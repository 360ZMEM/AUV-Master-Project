from types import SimpleNamespace
from pathlib import Path
import time

import pytest

from auv_viz_bridge.inspection_geometry import inspection_geometry
from auv_viz_bridge.inspection_status import InspectionStatus


def tracking():
    return {"estimated_cable_xy_m": [4., 6.], "burial_depth_m": 2., "cable_heading_deg": 0.,
            "diagnostics": {"inspection_enabled": True, "lateral_valid": True,
                            "depth_valid": False, "observation_line_sigma_m": .3, "fwhm_width_m": 8.}}


def test_depth_flag_overrides_cached_scalar_and_projection_is_labelled():
    result = inspection_geometry(tracking(), 12., .1)
    assert result.position_ned == (4.,6.,12.)
    assert result.burial_m is None
    assert "PROJECTION" in result.label


@pytest.mark.parametrize("age", [1.51, -1., float("nan"), float("inf")])
def test_stale_or_invalid_age_clears_all_estimate_geometry(age):
    result = inspection_geometry(tracking(),12.,age)
    assert result.position_ned is None and result.width_m is None
    assert result.burial_m is None and result.lateral_sigma_m is None


def test_lateral_invalid_and_nonfinite_position_are_not_truth_filled():
    data = tracking()
    data["diagnostics"]["lateral_valid"] = False
    assert inspection_geometry(data,12.,0.).position_ned is None
    data = tracking()
    data["estimated_cable_xy_m"][0] = float("nan")
    assert inspection_geometry(data,12.,0.).position_ned is None


def test_burial_sigma_is_never_relabelled_as_lateral_uncertainty():
    data = tracking()
    data["diagnostics"].pop("observation_line_sigma_m")
    data["diagnostics"]["fwhm_burial_depth_sigma_m"] = .001
    assert inspection_geometry(data,12.,0.).lateral_sigma_m is None


def test_qualified_depth_uses_reference_plane_and_explicit_flag():
    data = tracking()
    data["diagnostics"]["depth_valid"] = True
    result = inspection_geometry(data,12.,0.)
    assert result.position_ned == (4.,6.,14.)
    assert result.burial_m == 2.


def test_render_path_deletes_old_markers_and_never_reads_truth(monkeypatch):
    monkeypatch.setenv('AUV_PROJECT_ROOT', str(Path(__file__).resolve().parents[4]))
    from builtin_interfaces.msg import Time
    from visualization_msgs.msg import Marker
    from auv_viz_bridge.zenoh_viz_bridge_node import ZenohVizBridgeNode

    class Publisher:
        def __init__(self): self.messages = []
        def publish(self, value): self.messages.append(value)

    node = SimpleNamespace(_tracking=tracking(), _inspection_geometry_enabled=True,
                           _inspection_status=InspectionStatus(),
                           _tracking_received_monotonic_s=time.monotonic(),
                           virtual_env=SimpleNamespace(config=SimpleNamespace(seabed_z_m=12.)))
    for name in ("cable_estimate_pub", "burial_estimate_pub", "position_uncertainty_pub",
                 "fwhm_span_pub", "perception_label_pub", "perception_text_pub", "magnetic_vector_pub"):
        setattr(node, name, Publisher())
    node._publish_inspection_geometry = lambda **kw: ZenohVizBridgeNode._publish_inspection_geometry(node, **kw)
    # Unusable truth objects deliberately prove that the inspection branch
    # cannot fill missing coordinates from the scene's cable truth.
    def render():
        ZenohVizBridgeNode._publish_perception_geometry(node, object(), object(), object(), {},
                                                       frame_id="map", stamp=Time())
    render()
    assert node.cable_estimate_pub.messages[-1].action == Marker.ADD
    assert node.cable_estimate_pub.messages[-1].scale.z == .06
    assert node.cable_estimate_pub.messages[-1].lifetime.sec == 2
    assert node.burial_estimate_pub.messages[-1].action == Marker.DELETE
    node._tracking_received_monotonic_s = time.monotonic() - 2.
    render()
    for name in ("cable_estimate_pub", "burial_estimate_pub", "position_uncertainty_pub",
                 "fwhm_span_pub", "perception_label_pub", "magnetic_vector_pub"):
        assert getattr(node,name).messages[-1].action == Marker.DELETE
    node._inspection_geometry_enabled = False
    node._tracking = {"mode": "SENSOR_DEGRADED"}
    render()
    assert node.cable_estimate_pub.messages[-1].action == Marker.DELETE


def test_field_review_viz_never_invents_scene_on_missing_or_stale_zenoh(monkeypatch):
    monkeypatch.setenv('AUV_PROJECT_ROOT', str(Path(__file__).resolve().parents[4]))
    from auv_viz_bridge.zenoh_viz_bridge_node import ZenohVizBridgeNode
    import auv_viz_bridge.zenoh_viz_bridge_node as viz_module

    monkeypatch.setattr(viz_module.rclpy, 'ok', lambda: True)
    cleared, scenes, states = [], [], []
    node = SimpleNamespace(
        allow_synthetic_scene_fallback=False,
        mock_fallback_timeout_s=3.,
        _live_layer_monotonic_s={},
        _scene_live_signature=None,
        _live_truth=None, _live_terrain=None, _live_cable=None,
        _live_trail=None, _live_range=None,
        _publish_mission_display_state=lambda: states.append(True),
        _clear_untrusted_scene_markers=lambda: cleared.append(True),
        _publish_scene=lambda *args: scenes.append(args),
    )
    ZenohVizBridgeNode._on_timer(node)
    assert len(states) == 1 and len(cleared) == 1 and not scenes

    node._live_truth = {'position_ned': [0., 0., -10.], 'rpy_ned': [0., 0., 0.]}
    node._live_layer_monotonic_s['truth'] = time.monotonic()
    ZenohVizBridgeNode._on_timer(node)
    assert len(scenes) == 1
    assert scenes[-1][0] == {} and scenes[-1][1] == {}
    assert scenes[-1][3] == {} and scenes[-1][4] == {}

    node._live_cable = {'points_ned': [[0., 0., -12.], [1., 0., -12.]]}
    node._live_layer_monotonic_s['cable'] = time.monotonic()
    ZenohVizBridgeNode._on_timer(node)
    assert scenes[-1][1] == node._live_cable
    node._live_layer_monotonic_s['cable'] = time.monotonic() - 4.
    ZenohVizBridgeNode._on_timer(node)
    assert scenes[-1][1] == {}

    node._live_layer_monotonic_s['truth'] = time.monotonic() - 4.
    ZenohVizBridgeNode._on_timer(node)
    assert len(cleared) == 5 and len(scenes) == 3


def test_field_review_does_not_keep_old_track_label():
    from auv_viz_bridge.zenoh_viz_bridge_node import ZenohVizBridgeNode

    class Publisher:
        def __init__(self): self.messages = []
        def publish(self, value): self.messages.append(value.data)

    output = Publisher()
    node = SimpleNamespace(
        _emergency_active=False, _tracking={'mode': 'TRACK'},
        _tracking_received_monotonic_s=time.monotonic() - 4.,
        allow_synthetic_scene_fallback=False, mock_fallback_timeout_s=3.,
        mission_display_state_pub=output,
    )
    ZenohVizBridgeNode._publish_mission_display_state(node)
    assert output.messages[-1] == 'STATUS_STALE'
    node._tracking_received_monotonic_s = time.monotonic()
    ZenohVizBridgeNode._publish_mission_display_state(node)
    assert output.messages[-1] == 'TRACK'


def test_inspection_target_is_estimate_projection_and_expires():
    from builtin_interfaces.msg import Time
    from visualization_msgs.msg import Marker
    from auv_viz_bridge.zenoh_viz_bridge_node import ZenohVizBridgeNode

    class Publisher:
        def __init__(self): self.messages = []
        def publish(self, msg): self.messages.append(msg)

    node = SimpleNamespace(
        _tracking=tracking(), _tracking_received_monotonic_s=time.monotonic(),
        virtual_env=SimpleNamespace(config=SimpleNamespace(seabed_z_m=12.)),
        _inspection_status=InspectionStatus(), _emergency_active=False,
        cable_target_pub=Publisher(), detection_link_pub=Publisher(), mission_label_pub=Publisher())
    render = lambda: ZenohVizBridgeNode._publish_inspection_mission_target(
        node, [0.,0.,8.], frame_id='world', stamp=Time())
    render()
    marker = node.cable_target_pub.messages[-1]
    # Marker helpers convert NED depth to the world frame's upward Z.
    assert (marker.pose.position.x, marker.pose.position.y, marker.pose.position.z) == (4.,6.,-12.)
    assert marker.scale.z == .06
    node._tracking_received_monotonic_s = time.monotonic() - 2.
    render()
    assert node.cable_target_pub.messages[-1].action == Marker.DELETE
    assert node.detection_link_pub.messages[-1].action == Marker.DELETE


def test_field_review_does_not_forward_simulator_ground_truth():
    from auv_viz_bridge.zenoh_viz_bridge_node import ZenohVizBridgeNode

    node = SimpleNamespace(publish_sim_ground_truth=False)
    ZenohVizBridgeNode._on_ground_truth(
        node, {'position_ned': [1., 2., 3.], 'rpy_ned': [0., 0., 0.]})
