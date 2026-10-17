"""Mission injector carries reviewed target identity only when configured."""

import json
import unittest
from types import SimpleNamespace

import rclpy

from auv_decision_ros.cable_mission_autostart_node import CableMissionAutostartNode


class CableMissionAutostartIdentityTests(unittest.TestCase):
    def _publish_once(self, args):
        rclpy.init(args=['--ros-args', *args])
        node = CableMissionAutostartNode()
        try:
            messages = []
            node.publisher = SimpleNamespace(publish=messages.append)
            node.cable_publisher = SimpleNamespace(publish=messages.append)
            node.start_delay_s = 0.
            node.start_time_s = float(node.get_clock().now().nanoseconds) * 1e-9 - 1.
            node._on_timer()
            self.assertEqual(len(messages), 2)
            return json.loads(messages[0].data), json.loads(messages[1].data)
        finally:
            node.destroy_node()
            rclpy.shutdown()

    def test_reviewed_ids_match_on_both_topics(self):
        general, cable = self._publish_once([
            '-p', 'mission_id:=survey_mission_01',
            '-p', 'target_id:=cable_A',
        ])
        self.assertEqual(general, cable)
        self.assertEqual(general['mission_id'], 'survey_mission_01')
        self.assertEqual(general['target_id'], 'cable_A')

    def test_legacy_default_omits_ids(self):
        general, cable = self._publish_once([])
        self.assertEqual(general, cable)
        self.assertNotIn('mission_id', general)
        self.assertNotIn('target_id', general)


if __name__ == '__main__':
    unittest.main()
