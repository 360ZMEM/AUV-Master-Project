"""Bounded PC104-time join of body DVL and independently validated IMU.

The $AUV packet supplies DVL velocity in body coordinates and the PC104 time
when that DVL sample was parsed. IMV1 supplies a separately checked attitude
and the PC104 time when its source frame was completely received. This join
never uses the legacy $AUV attitude for rotation.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math

from common.imu_provenance_sidecar import ImuProvenanceV1


@dataclass(frozen=True)
class BodyDvlSample:
    pc104_packet_uptime_ms: int
    pc104_dvl_uptime_ms: int
    velocity_xyz_mps: tuple[float, float, float]


@dataclass(frozen=True)
class DvlJoinResult:
    accepted: bool
    reason: str
    world_xyz_mps: tuple[float, float, float] | None = None
    stamp_s: float | None = None


def parse_body_dvl_json(data: str) -> BodyDvlSample:
    obj = json.loads(data)
    if not isinstance(obj, dict) or set(obj) != {
            'pc104_packet_uptime_ms', 'pc104_dvl_uptime_ms', 'velocity_xyz_mps'}:
        raise ValueError('invalid body DVL record fields')
    packet_ms, dvl_ms = obj['pc104_packet_uptime_ms'], obj['pc104_dvl_uptime_ms']
    xyz = obj['velocity_xyz_mps']
    if (not all(type(x) is int and 0 <= x <= 0x7fffffff for x in (packet_ms, dvl_ms))
            or not isinstance(xyz, list) or len(xyz) != 3
            or not all(type(x) in (int, float) and math.isfinite(x) for x in xyz)):
        raise ValueError('invalid body DVL record value')
    return BodyDvlSample(packet_ms, dvl_ms, tuple(float(x) for x in xyz))


def _rotate_body_to_world(quaternion_xyzw: tuple[float, float, float, float],
                          velocity_xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    qx, qy, qz, qw = quaternion_xyzw
    vx, vy, vz = velocity_xyz
    return (
        (1 - 2 * (qy*qy + qz*qz))*vx + 2*(qx*qy - qw*qz)*vy + 2*(qx*qz + qw*qy)*vz,
        2*(qx*qy + qw*qz)*vx + (1 - 2*(qx*qx + qz*qz))*vy + 2*(qy*qz - qw*qx)*vz,
        2*(qx*qz - qw*qy)*vx + 2*(qy*qz + qw*qx)*vy + (1 - 2*(qx*qx + qy*qy))*vz,
    )


def join_body_dvl_to_sidecar(
        dvl: BodyDvlSample, imu: ImuProvenanceV1,
        quaternion_xyzw: tuple[float, float, float, float],
        imu_stamp_s: float, now_ros_s: float,
        *, maximum_pair_gap_s: float = 0.15,
        maximum_rotation_between_samples_rad: float = math.radians(2.),
        maximum_receive_age_s: float = 0.50,
        maximum_packet_dvl_age_s: float = 0.50,
        maximum_speed_mps: float = 2.0) -> DvlJoinResult:
    if not all(math.isfinite(v) for v in (*quaternion_xyzw, imu_stamp_s, now_ros_s)):
        return DvlJoinResult(False, 'nonfinite_orientation_or_clock')
    if abs(sum(q*q for q in quaternion_xyzw) - 1.) > 1e-3:
        return DvlJoinResult(False, 'invalid_orientation_norm')
    speed = math.sqrt(sum(v*v for v in dvl.velocity_xyz_mps))
    if not math.isfinite(speed) or speed > maximum_speed_mps:
        return DvlJoinResult(False, 'dvl_speed_out_of_envelope')
    packet_age_ms = dvl.pc104_packet_uptime_ms - dvl.pc104_dvl_uptime_ms
    if packet_age_ms < 0 or packet_age_ms > maximum_packet_dvl_age_s * 1000.:
        return DvlJoinResult(False, 'dvl_sample_stale_in_uplink')
    pair_gap_ms = imu.pc104_receive_uptime_ms - dvl.pc104_dvl_uptime_ms
    if pair_gap_ms < 0 or pair_gap_ms > maximum_pair_gap_s * 1000.:
        return DvlJoinResult(False, 'dvl_imu_time_mismatch')
    pair_gap_s = pair_gap_ms / 1000.
    angular_rate = math.sqrt(imu.angular_rate_x_rps**2 + imu.angular_rate_y_rps**2
                             + imu.angular_rate_z_rps**2)
    if angular_rate * pair_gap_s > maximum_rotation_between_samples_rad:
        return DvlJoinResult(False, 'rotation_between_samples_too_large')
    dvl_stamp_s = imu_stamp_s - pair_gap_s
    if not 0. <= now_ros_s - dvl_stamp_s <= maximum_receive_age_s:
        return DvlJoinResult(False, 'dvl_ros_time_stale_or_future')
    return DvlJoinResult(True, 'body_dvl_rotated_with_sidecar_imu',
                         _rotate_body_to_world(quaternion_xyzw, dvl.velocity_xyz_mps),
                         dvl_stamp_s)
