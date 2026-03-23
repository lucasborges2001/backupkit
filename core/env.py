from __future__ import annotations

from pathlib import Path


def load_env_file(path: str | Path) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Env file not found: {path}")
    data: dict[str, str] = {}
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        data[key] = value
    return data
