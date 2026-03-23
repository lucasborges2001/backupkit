from __future__ import annotations

from pathlib import Path
from core.env import load_env_file
from core.yamlish import load_yamlish


class ConfigError(Exception):
    pass


def load_config(env_path: str, policy_path: str) -> dict:
    env = load_env_file(env_path)
    policy_file = Path(policy_path)
    if not policy_file.exists():
        raise ConfigError(f"Policy file not found: {policy_file}")
    policy = load_yamlish(policy_file.read_text(encoding='utf-8'))
    if not isinstance(policy, dict):
        raise ConfigError("Policy root must be a mapping")
    return {"env": env, "policy": policy}


def deep_get(obj: dict, path: str, default=None):
    cur = obj
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
