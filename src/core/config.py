import yaml
from pathlib import Path
from typing import Any

_config: dict = {}


def load(path: str = None) -> dict:
    """Load configuration from a YAML file. Defaults to config/default.yaml."""
    global _config
    if path is None:
        # src/core/ → go up two levels to reach the project root
        path = Path(__file__).parent.parent.parent / "config" / "default.yaml"
    with open(path, "r") as f:
        _config = yaml.safe_load(f) or {}
    return _config


def get(key: str, default: Any = None) -> Any:
    """
    Retrieve a config value by dot-separated key.
    e.g. get("obs.host") → _config["obs"]["host"]
    """
    keys = key.split(".")
    val = _config
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
    return val if val is not None else default
