from __future__ import annotations


def parse_scalar(value: str):
    value = value.strip()
    if value == "":
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if value.startswith("0") and value not in {"0", "0.0"} and not value.startswith("0."):
            raise ValueError
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def load_yamlish(text: str):
    lines = []
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].rstrip('\n\r')
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(' '))
        if indent % 2 != 0:
            raise ValueError(f"Indentation must use multiples of 2 spaces: {raw!r}")
        lines.append((indent, line.strip()))
    if not lines:
        return {}

    root = None
    stack = []  # entries: (indent, container, parent, parent_key)

    def attach_to_parent(parent, key, value):
        if isinstance(parent, dict):
            parent[key] = value
        elif isinstance(parent, list):
            parent.append(value)
        else:
            raise ValueError("Invalid YAML structure")

    i = 0
    while i < len(lines):
        indent, content = lines[i]
        while stack and indent < stack[-1][0]:
            stack.pop()

        parent = stack[-1][1] if stack else None

        if content.startswith('- '):
            item = content[2:].strip()
            if not isinstance(parent, list):
                raise ValueError(f"List item without list parent at line: {content}")
            if ': ' in item:
                key, value = item.split(':', 1)
                obj = {key.strip(): parse_scalar(value.strip())}
                parent.append(obj)
                stack.append((indent + 2, obj, parent, None))
            elif item.endswith(':'):
                obj = {item[:-1].strip(): {}}
                parent.append(obj)
                stack.append((indent + 2, obj[item[:-1].strip()], obj, item[:-1].strip()))
            else:
                parent.append(parse_scalar(item))
            i += 1
            continue

        if ':' not in content:
            raise ValueError(f"Invalid line: {content}")

        key, value = content.split(':', 1)
        key = key.strip()
        value = value.strip()

        next_line = lines[i + 1] if i + 1 < len(lines) else None
        next_is_child = bool(next_line and next_line[0] > indent)

        if not stack and root is None:
            root = {}
            stack.append((indent, root, None, None))
            parent = root
        elif parent is None:
            raise ValueError("Unexpected parser state")

        if value == "":
            if next_is_child and next_line[1].startswith('- '):
                container = []
            else:
                container = {}
            attach_to_parent(parent, key, container)
            stack.append((indent + 2, container, parent, key))
        else:
            attach_to_parent(parent, key, parse_scalar(value))
        i += 1

    return root or {}
