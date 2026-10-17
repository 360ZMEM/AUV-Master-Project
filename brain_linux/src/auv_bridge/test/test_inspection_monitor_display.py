from auv_bridge.bridge_node import AUVBridgeNode as BridgeNode


def test_inspection_monitor_cannot_show_unqualified_cached_depth():
    payload = dict(burial_depth_m=2., burial_sigma_m=.1,
                   diagnostics=dict(inspection_enabled=True, lateral_valid=True,
                                    depth_valid=False, fwhm_width_m=8., fwhm_valid=True))
    monitor = BridgeNode._build_cable_monitor_payload(payload)
    assert monitor['burial_depth_m'] is None and monitor['burial_sigma_m'] is None
    assert monitor['lateral_valid'] is True and monitor['fwhm_width_m'] == 8.
    payload['diagnostics']['depth_valid'] = True
    assert BridgeNode._build_cable_monitor_payload(payload)['burial_depth_m'] == 2.


def test_legacy_monitor_remains_compatible():
    assert BridgeNode._build_cable_monitor_payload({'burial_depth_m': 2.})['burial_depth_m'] == 2.
