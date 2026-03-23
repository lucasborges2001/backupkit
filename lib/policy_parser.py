#!/usr/bin/env python3
import json
import sys


def parse_scalar(value: str):
    value = value.strip()
    if value == "":
        return ""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.isdigit():
        return int(value)
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def next_nonempty(lines, start):
    i = start
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if stripped and not stripped.startswith('#'):
            return i, raw
        i += 1
    return None, None


def parse_block(lines, start, indent):
    result = {}
    i = start
    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith('#'):
          i += 1
          continue
        current_indent = len(raw) - len(raw.lstrip(' '))
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ValueError(f"Indentación inválida en línea {i+1}: {raw!r}")
        line = raw.strip()
        if line.startswith('- '):
            raise ValueError(f"Lista inesperada en línea {i+1}: {raw!r}")
        if ':' not in line:
            raise ValueError(f"Línea inválida {i+1}: {raw!r}")
        key, rest = line.split(':', 1)
        key = key.strip()
        rest = rest.strip()
        if rest:
            result[key] = parse_scalar(rest)
            i += 1
            continue
        ni, next_raw = next_nonempty(lines, i + 1)
        if next_raw is None:
            result[key] = {}
            i += 1
            continue
        next_indent = len(next_raw) - len(next_raw.lstrip(' '))
        next_line = next_raw.strip()
        if next_indent <= current_indent:
            result[key] = {}
            i += 1
        elif next_line.startswith('- '):
            items, new_i = parse_list(lines, i + 1, next_indent)
            result[key] = items
            i = new_i
        else:
            child, new_i = parse_block(lines, i + 1, next_indent)
            result[key] = child
            i = new_i
    return result, i


def parse_list(lines, start, indent):
    items = []
    i = start
    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith('#'):
            i += 1
            continue
        current_indent = len(raw) - len(raw.lstrip(' '))
        if current_indent < indent:
            break
        if current_indent != indent:
            raise ValueError(f"Indentación inválida en lista línea {i+1}: {raw!r}")
        line = raw.strip()
        if not line.startswith('- '):
            break
        items.append(parse_scalar(line[2:].strip()))
        i += 1
    return items, i


def main():
    if len(sys.argv) != 2:
        print("uso: policy_parser.py <policy.yml>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    data, _ = parse_block(lines, 0, 0)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
