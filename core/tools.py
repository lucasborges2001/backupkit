from __future__ import annotations

import shutil
import sys

TOOL_PROVIDERS = {
    "mysql_dump_client": ["mysqldump"],
    "mysql_query_client": ["mysql"],
    "gzip_provider": ["gzip"],
    "hash_provider": ["sha256sum"] if sys.platform != 'win32' else ["powershell", "pwsh"],
}


def resolve_tool(tool_id: str):
    candidates = TOOL_PROVIDERS.get(tool_id, [tool_id])
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None
