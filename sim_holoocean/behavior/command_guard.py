import time
import numpy as np
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for folder in [PROJECT_ROOT, PROJECT_ROOT / "common"]:
    folder = str(folder)
    if folder not in sys.path:
        sys.path.insert(0, folder)

from common.protocol import KEY_BOTTOM, KEY_LEFT, KEY_RIGHT, KEY_THRUST, KEY_TOP, normalize_control_command


class CommandGuard:
    def __init__(self, cfg):
        self.cfg = cfg
        self.timeout_s = float(cfg.get("cmd_timeout_s", 0.5))
        self.require_first_cmd = bool(cfg.get("require_first_cmd", False))
        self.start_time = time.time()

        self.fin_abs_max = float(cfg.get("fin_abs_max", 30.0))
        self.thrust_min = float(cfg.get("thrust_min", -100.0))
        self.thrust_max = float(cfg.get("thrust_max", 100.0))

    def _extract_command(self, cmd_msg):
        if cmd_msg is None:
            return None
        try:
            norm = normalize_control_command(cmd_msg)
        except Exception:
            return None
        return np.asarray(
            [
                norm[KEY_RIGHT],
                norm[KEY_TOP],
                norm[KEY_LEFT],
                norm[KEY_BOTTOM],
                norm[KEY_THRUST],
            ],
            dtype=float,
        )

    def sanitize(self, cmd_msg, previous_cmd, cmd_ts):
        now = time.time()
        cmd = self._extract_command(cmd_msg)

        if cmd is None or cmd.size != 5:
            if self.require_first_cmd and (now - self.start_time) < self.timeout_s:
                return np.zeros(5, dtype=float)
            return np.asarray(previous_cmd, dtype=float).reshape(5)

        if now - float(cmd_ts) > self.timeout_s:
            return np.asarray(previous_cmd, dtype=float).reshape(5)

        cmd = cmd.copy()
        cmd[:4] = np.clip(cmd[:4], -self.fin_abs_max, self.fin_abs_max)
        cmd[4] = np.clip(cmd[4], self.thrust_min, self.thrust_max)
        return cmd
