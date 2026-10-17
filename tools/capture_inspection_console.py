"""Capture the real Qt interface with labelled synthetic status, no transports."""
import argparse
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'console_soft/auv_console_pyside6'))
from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    with patch.object(MainWindow, 'load_configuration', lambda self: None), \
            patch.object(MainWindow, 'connect_signals', lambda self: None):
        window = MainWindow()
    for name in ('tx_timer', 'beidou_timer', 'map_refresh_timer', 'inspection_status_timer'):
        getattr(window, name).stop()
    window.setWindowTitle('AUV 任务控制台 — 合成显示检查／无通信')
    window.resize(1366, 900)
    window.tab_widget.setCurrentIndex(3)
    window.show()
    status = dict(command_sequence=1, timestamp_s=1001.,
                  autonomous_execution_authorized=False, authority_reason='endpoint_hold',
                  arbiter_mode='AUTONOMOUS', arbiter_source='NONE', guard_state='ACTIVE',
                  localization_status='LOCALIZED_DEPTH_PENDING', localization_status_fresh=True,
                  task_status='SOFTWARE_ROUTE_COMPLETE', task_status_fresh=True)
    for sequence, (name, outcome, age) in enumerate([
            ('console_route_complete', 'SOFTWARE_ROUTE_COMPLETE', 0.),
            ('console_suspended', 'SUSPENDED', 0.),
            ('console_status_stale', 'SOFTWARE_ROUTE_COMPLETE', 2.)], 1):
        status.update(command_sequence=sequence, timestamp_s=1000.+sequence, task_status=outcome,
                      authority_reason='endpoint_hold' if outcome == 'SOFTWARE_ROUTE_COMPLETE'
                      else 'inspection_recovery_required')
        window._inspection_operational_view.accept(status, now=time.monotonic()-age)
        window.update_cable_monitor_display(dict(
            mode='TRACK', inspection_enabled=True, lateral_valid=True, depth_valid=False,
            burial_depth_m=2., cross_track_m=.8, route_progress_m=80.,
            fwhm_width_m=8., fwhm_valid=True, acceptance_flags_text='depth_not_calibrated'))
        window.refresh_inspection_authority_display()
        assert '2.00 m' not in window.lbl_cable_metrics.text()
        if age:
            assert '未知' in window.lbl_cable_ready.text()
            assert '8.00' not in window.lbl_cable_quality.text()
        window.status_bar.showMessage('合成状态显示检查；无 ROS／Zenoh／UDP 通信，不是任务采证截图。')
        app.processEvents()
        if not window.grab().save(str(args.output_dir / (name+'.png'))):
            raise RuntimeError('Screenshot save failed')
    window.close()


if __name__ == '__main__':
    main()
