from foxglove_layout_project.config.topics import TOPICS, with_topic_prefix
from foxglove_layout_project.generator.layout_builder import build_auv_layout


def test_current_layout_preserves_cable_layers_without_legacy_ready_or_mock_vehicle():
    layout = build_auv_layout(profile='inspection-v2')
    panels = layout['configById']
    assert not any(key.startswith(('Gauge!', 'Indicator!')) for key in panels)
    scene = panels['3D!inspection_scene']['topics']
    for topic in (TOPICS.cable_marker, TOPICS.search_pattern, TOPICS.search_corridor,
                  TOPICS.cable_target, TOPICS.history_trail, TOPICS.fwhm_span):
        assert scene[topic]['visible']
    assert not scene[TOPICS.decoupled_vehicle]['visible']
    assert TOPICS.cable_operational_status in str(panels)
    assert TOPICS.cable_industrial_ready not in str(panels)


def test_new_status_topic_obeys_namespace_prefix():
    topics = with_topic_prefix(TOPICS, '/review')
    layout = build_auv_layout(topics=topics, profile='inspection-v2')
    assert layout['configById']['RawMessages!inspection_bridge']['topicPath'] == '/review/auv/cable/operational_status'
