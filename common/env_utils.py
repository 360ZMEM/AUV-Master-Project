import os
from pathlib import Path
from datetime import datetime
import yaml

_RUN_DIR = None

def get_data_root() -> Path:
    """获取数据根目录。优先使用环境变量，其次配置文件，最后回退 /tmp/auv_data"""
    env_root = os.environ.get('AUV_DATA_ROOT')
    if env_root:
        return Path(env_root)
    
    project_root = Path(__file__).resolve().parents[1]
    params_path = project_root / 'brain_linux' / 'config' / 'params.yaml'
    
    data_root = "/tmp/auv_data"
    if params_path.exists():
        try:
            with open(params_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
                if isinstance(cfg, dict) and 'auv_data_root' in cfg:
                    data_root = cfg['auv_data_root']
        except Exception:
            pass
            
    return Path(data_root)

def get_output_dir(sub_name: str) -> Path:
    """自动创建时间戳文件夹，并在其下创建子文件夹（或在子文件夹下创建时间戳）
    此处采用 {data_root}/{sub_name}/{datetime} 的结构，确保同一 sub_name 下归档清晰。
    """
    global _RUN_DIR
    root = get_data_root()
    if _RUN_DIR is None:
        _RUN_DIR = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = root / sub_name / _RUN_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

def deep_update(d, u):
    """递归更新字典"""
    import collections.abc
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = deep_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d

def load_config_with_overrides(base_path: str) -> dict:
    """加载基础 yaml 并尝试用 overrides 覆盖"""
    cfg = {}
    base_p = Path(base_path)
    if base_p.exists():
        with open(base_p, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if isinstance(data, dict):
                cfg = data
                
    override_path = get_data_root() / "config_overrides" / "params.yaml"
    if override_path.exists():
        try:
            with open(override_path, 'r', encoding='utf-8') as f:
                override_data = yaml.safe_load(f)
                if isinstance(override_data, dict):
                    cfg = deep_update(cfg, override_data)
        except Exception:
            pass
            
    return cfg
