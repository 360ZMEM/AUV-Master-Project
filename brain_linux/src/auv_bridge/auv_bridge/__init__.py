from __future__ import annotations

import os
import sys
from pathlib import Path


def _resolve_project_root() -> Path:
	env_root = Path(str(os.environ.get('AUV_PROJECT_ROOT', ''))).expanduser() if os.environ.get('AUV_PROJECT_ROOT') else None
	if env_root and (env_root / 'common').exists():
		return env_root

	try:
		from ament_index_python.packages import get_package_share_directory

		share_dir = Path(get_package_share_directory('auv_bridge')).resolve()
		candidate = share_dir.parents[3]
		if (candidate / 'common').exists():
			return candidate
	except Exception:
		pass

	current = Path(__file__).resolve()
	for parent in current.parents:
		if (parent / 'common').exists() and (parent / 'brain_linux').exists():
			return parent

	raise RuntimeError('cannot resolve AUV project root for auv_bridge package')


PROJECT_ROOT = _resolve_project_root()

for folder in (PROJECT_ROOT, PROJECT_ROOT / 'common'):
	folder_str = str(folder)
	if folder_str not in sys.path:
		sys.path.insert(0, folder_str)
