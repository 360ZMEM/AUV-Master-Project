#!/usr/bin/env python3
"""Inspect guarded control messages through the real bridge and loopback $CKTH endpoint."""
import json
import os
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('AUV_PROJECT_ROOT', str(ROOT))
data_root = ROOT / 'tmp/inspection_bridge_data'
data_root.mkdir(parents=True, exist_ok=True)
os.environ['AUV_DATA_ROOT'] = str(data_root)

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from auv_interfaces.msg import MpcCmd
from auv_cable_tracking_v2.inspection_bridge_node import InspectionBridgeNode
from common.enums import ArbiterMode, ControlModeByte, WorkInstruction
from common.protocol import (KEY_BOTTOM,KEY_CONTROL_MODE_BYTE,KEY_LEFT,KEY_RIGHT,KEY_THRUST,
                             KEY_TOP,KEY_TOTAL_VOLTAGE_V,parse_downlink_packet_to_payload)
import yaml


def main():
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise SystemExit('Use ROS_LOCALHOST_ONLY=1 and a dedicated ROS_DOMAIN_ID')
    rows = json.loads((ROOT/'AUV-Master-Mag/results/v2/inspection_ros_controller_installed_20260926/trajectory.json').read_text())
    active_row = max((row for row in rows if row.get('thrust_percent',0)>0 and row['mode']=='track'),
                     key=lambda row: row['thrust_percent'])
    base = yaml.safe_load((ROOT/'brain_linux/src/auv_cable_tracking_v2/config/inspection_bridge_passive.yaml').read_text())
    sink = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sink.bind(('127.0.0.1',0))
    sink.settimeout(2.)
    base['bridge']['protocol_udp']['remote_port'] = sink.getsockname()[1]
    config = data_root/'bridge_loopback_params.yaml'
    config.write_text(yaml.safe_dump(base))
    rclpy.init(args=['--ros-args','-p',f'params_file:={config}','-p','passive_mode:=false',
                     '-p','bridge_backend:=protocol_udp'])
    bridge = InspectionBridgeNode()
    bridge._command_keepalive_timer.cancel()
    peer = Node('inspection_bridge_audit_peer')
    pub = peer.create_publisher(MpcCmd,'/auv/control/mpc_cmd',10)
    executor = SingleThreadedExecutor()
    executor.add_node(bridge)
    executor.add_node(peer)
    evidence = []

    def receive(stage):
        packet,_ = sink.recvfrom(2048)
        assert len(packet)==72
        payload = parse_downlink_packet_to_payload(packet)
        entry = {'stage':stage,'packet_hex':packet.hex(), 'payload':payload,
                 'arbiter_source':bridge.last_arbiter_decision.arbiter_source.value}
        evidence.append(entry)
        return payload

    def zero(payload):
        return all(abs(float(payload[key])) <= .1 for key in (KEY_RIGHT,KEY_TOP,KEY_LEFT,KEY_BOTTOM,KEY_THRUST))

    try:
        bridge.latest_sensor_status_payload.update(confidence=1.,leak_level=0)
        bridge.latest_bridge_telemetry_payload = {KEY_TOTAL_VOLTAGE_V:50.}
        bridge.latest_protocol_telemetry_ts = time.time()
        pc = {KEY_CONTROL_MODE_BYTE:int(ControlModeByte.JETSON_PROTOCOL), 'work_instruction':0,
              KEY_THRUST:0.,KEY_RIGHT:0.,KEY_TOP:0.,KEY_LEFT:0.,KEY_BOTTOM:0.}
        bridge.handle_pc_raw_command(pc)
        initial = receive('autonomy_request_before_pid')
        assert zero(initial) and bridge.command_arbiter.active_mode == ArbiterMode.AUTONOMOUS
        deadline=time.monotonic()+3
        while pub.get_subscription_count()==0:
            assert time.monotonic()<deadline
            executor.spin_once(timeout_sec=.01)
        cmd=MpcCmd()
        cmd.header.stamp=bridge.get_clock().now().to_msg()
        cmd.source,cmd.valid,cmd.healthy='INSPECTION_REPLAY',True,True
        for field in ('thrust_percent','right_fin_deg','top_fin_deg','left_fin_deg','bottom_fin_deg'):
            setattr(cmd,field,float(active_row[field]))
        cmd.target_depth_m=10.
        pub.publish(cmd)
        deadline=time.monotonic()+3
        while bridge.last_arbiter_decision.arbiter_source.value != 'JETSON_MPC':
            assert time.monotonic()<deadline
            executor.spin_once(timeout_sec=.01)
        active=receive('healthy_pid_replay')
        assert active[KEY_THRUST]>0 and int(active[KEY_CONTROL_MODE_BYTE])==int(ControlModeByte.JETSON_PROTOCOL)
        assert active['main_motor_rpm'] == round(active_row['thrust_percent'] * 15)

        # No new MpcCmd arrives. The controller and its watchdog are absent.
        # A keepalive must itself revoke the cached positive-thrust decision.
        time.sleep(.56)
        bridge.latest_protocol_telemetry_ts=time.time()
        bridge._on_command_keepalive()
        stale=receive('controller_process_disappeared')
        assert zero(stale) and bridge.last_arbiter_decision.arbiter_source.value=='SAFETY_FALLBACK'

        bridge.handle_pc_raw_command({**pc,KEY_CONTROL_MODE_BYTE:int(ControlModeByte.REMOTE_CONTROL),
                                      'work_instruction':int(WorkInstruction.TASK_CANCEL)})
        cancelled=receive('manual_cancel')
        assert zero(cancelled) and bridge.command_arbiter.active_mode==ArbiterMode.REMOTE
        bridge.latest_protocol_telemetry_ts=time.time()
        bridge._on_command_keepalive()
        retained=receive('manual_priority_retained')
        assert zero(retained) and bridge.command_arbiter.active_mode==ArbiterMode.REMOTE

        out=ROOT/'AUV-Master-Mag/results/v2/inspection_bridge_loopback_20260926'
        out.mkdir(parents=True,exist_ok=True)
        summary={'stages':[item['stage'] for item in evidence], 'captured_packets':len(evidence),
                 'positive_thrust_replayed_from_pid':True,'lost_controller_fallback_zero':True,
                 'manual_priority_retained':True,'transport':'real protocol_udp backend to local UDP sink',
                 'hardware_connected':False,
                 'replayed_pid_thrust_percent':active_row['thrust_percent'],
                 'encoded_main_motor_rpm':active['main_motor_rpm']}
        (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        (out/'packets.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print(json.dumps(summary))
    finally:
        executor.remove_node(bridge)
        executor.remove_node(peer)
        bridge.destroy_node()
        peer.destroy_node()
        executor.shutdown()
        rclpy.shutdown()
        sink.close()


if __name__=='__main__':
    main()
