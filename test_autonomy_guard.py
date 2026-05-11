from brain_linux.src.auv_bridge.auv_bridge.autonomy_guard import AutonomyGuard, DenyReason

def test_storage_usage():
    guard = AutonomyGuard()
    # Mock telemetry
    telemetry = {
        'total_voltage_v': 48.0,
        'telemetry_freshness_ms': 100.0,
        'storage_usage': 0.95
    }
    sensor = {
        'leak_level': 0,
        'confidence': 1.0
    }
    decision = guard.request_activation(sensor_status=sensor, telemetry_status=telemetry)
    print("Decision:", decision.deny_reason)
    assert decision.deny_reason == DenyReason.LOW_CONFIDENCE

if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath('.'))
    test_storage_usage()
    print("AutonomyGuard storage_usage test passed!")
