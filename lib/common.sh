#!/usr/bin/env bash
set -euo pipefail

bk_now_iso() { date '+%Y-%m-%d %H:%M:%S'; }
bk_now_tag() { date '+%Y-%m-%d_%H%M%S'; }
bk_log() { printf '[%s] %s\n' "$(bk_now_iso)" "$*"; }
bk_fail() { bk_log "ERROR: $*"; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || bk_fail "Falta comando requerido: $1"
}

json_get() {
  local json_file="$1"
  local expr="$2"
  python3 - "$json_file" "$expr" <<'PY'
import json, sys
path = sys.argv[1]
expr = sys.argv[2]
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
cur = data
for part in expr.split('.'):
    if part == '':
        continue
    if isinstance(cur, dict):
        cur = cur.get(part)
    else:
        cur = None
        break
if cur is None:
    print("")
elif isinstance(cur, (dict, list)):
    print(json.dumps(cur, ensure_ascii=False))
else:
    print(cur)
PY
}

json_list_lines() {
  local json_file="$1"
  local expr="$2"
  python3 - "$json_file" "$expr" <<'PY'
import json, sys
path = sys.argv[1]
expr = sys.argv[2]
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
cur = data
for part in expr.split('.'):
    if part == '':
        continue
    if isinstance(cur, dict):
        cur = cur.get(part)
    else:
        cur = None
        break
if isinstance(cur, list):
    for item in cur:
        if isinstance(item, (dict, list)):
            print(json.dumps(item, ensure_ascii=False))
        else:
            print(item)
PY
}

run_backupkit() {
  local env_file="$1"
  local policy_file="$2"

  [[ -f "$env_file" ]] || bk_fail "No existe env: $env_file"
  [[ -f "$policy_file" ]] || bk_fail "No existe policy: $policy_file"

  require_cmd python3
  require_cmd gzip
  require_cmd sha256sum
  require_cmd mysql
  require_cmd mysqldump
  require_cmd mysqladmin
  require_cmd curl

  set -a
  source "$env_file"
  set +a

  local parser="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/policy_parser.py"
  local policy_json
  policy_json="$(mktemp)"
  python3 "$parser" "$policy_file" > "$policy_json"

  local project_name out_dir daily_keep restore_prefix telegram_enabled
  project_name="$(json_get "$policy_json" project.name)"
  out_dir="$(json_get "$policy_json" backup.out_dir)"
  daily_keep="$(json_get "$policy_json" retention.daily_keep)"
  restore_prefix="$(json_get "$policy_json" mysql.restore_test_db_prefix)"
  telegram_enabled="$(json_get "$policy_json" notifications.telegram.enabled)"

  [[ -n "$project_name" ]] || bk_fail "policy inválida: falta project.name"
  [[ -n "$out_dir" ]] || bk_fail "policy inválida: falta backup.out_dir"
  [[ -n "$daily_keep" ]] || daily_keep="7"
  [[ -n "$restore_prefix" ]] || restore_prefix="bk_restore"

  local run_id ts base_dir run_dir lock_file
  ts="$(bk_now_tag)"
  base_dir="$out_dir/$project_name"
  run_dir="$base_dir/$ts"
  lock_file="$base_dir/.backupkit.lock"

  mkdir -p "$run_dir"
  exec 9>"$lock_file"
  flock -n 9 || bk_fail "Ya hay una ejecución en curso"

  local report_json="$run_dir/report.json"
  local dump_sql="$run_dir/${project_name}_${ts}.sql"
  local dump_gz="$dump_sql.gz"
  local hash_file="$dump_gz.sha256"
  local full_tmp="$run_dir/full.sql"
  local schema_tmp="$run_dir/schema_only.sql"
  local combined_sql="$dump_sql"
  local started_at ended_at duration_sec size_bytes size_h sha_short stage msg
  started_at="$(date +%s)"
  stage="precheck"

  : "${MYSQL_HOST:?Falta MYSQL_HOST en .env}"
  : "${MYSQL_PORT:?Falta MYSQL_PORT en .env}"
  : "${MYSQL_USER:?Falta MYSQL_USER en .env}"
  : "${MYSQL_PASSWORD:?Falta MYSQL_PASSWORD en .env}"
  : "${MYSQL_DATABASE:?Falta MYSQL_DATABASE en .env}"

  export MYSQL_PWD="$MYSQL_PASSWORD"

  bk_log "Precheck MySQL"
  mysqladmin ping -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" --silent >/dev/null || bk_fail "MySQL no responde"

  stage="dump-full"
  bk_log "Dump full"
  mapfile -t excludes < <(json_list_lines "$policy_json" mysql.exclude_tables)
  mapfile -t schema_only < <(json_list_lines "$policy_json" mysql.schema_only_tables)

  local dump_args=(--host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" --single-transaction --quick --routines --triggers --events "$MYSQL_DATABASE")
  local table
  for table in "${excludes[@]:-}"; do
    [[ -n "$table" ]] && dump_args+=(--ignore-table="$MYSQL_DATABASE.$table")
  done
  for table in "${schema_only[@]:-}"; do
    [[ -n "$table" ]] && dump_args+=(--ignore-table="$MYSQL_DATABASE.$table")
  done
  mysqldump "${dump_args[@]}" > "$full_tmp"

  : > "$schema_tmp"
  if [[ ${#schema_only[@]} -gt 0 ]]; then
    stage="dump-schema-only"
    bk_log "Dump schema-only"
    for table in "${schema_only[@]}"; do
      [[ -z "$table" ]] && continue
      mysqldump --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" --no-data "$MYSQL_DATABASE" "$table" >> "$schema_tmp"
      printf '\n' >> "$schema_tmp"
    done
  fi

  cat "$full_tmp" "$schema_tmp" > "$combined_sql"
  [[ -s "$combined_sql" ]] || bk_fail "El dump quedó vacío"

  stage="compress"
  bk_log "Compress gzip"
  gzip -c "$combined_sql" > "$dump_gz"
  [[ -s "$dump_gz" ]] || bk_fail "El gzip quedó vacío"

  stage="hash"
  bk_log "SHA256"
  sha256sum "$dump_gz" > "$hash_file"
  sha_short="$(cut -c1-8 "$hash_file")"

  stage="restore"
  local restore_db="${restore_prefix}_${project_name}_$(date +%s)"
  bk_log "Restore test en $restore_db"
  mysql --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" -e "CREATE DATABASE \`$restore_db\`;"
  trap 'mysql --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" -e "DROP DATABASE IF EXISTS \`'$restore_db'\`;" >/dev/null 2>&1 || true' EXIT
  gunzip -c "$dump_gz" | mysql --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" "$restore_db"

  stage="validators"
  bk_log "Validators SQL"
  local validator_failed=0
  local vf
  mapfile -t validator_files < <(json_list_lines "$policy_json" validators.sql_files)
  if [[ ${#validator_files[@]} -gt 0 ]]; then
    for vf in "${validator_files[@]}"; do
      [[ -z "$vf" ]] && continue
      [[ -f "$vf" ]] || bk_fail "Validator no existe: $vf"
      if ! mysql --batch --raw --skip-column-names --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" "$restore_db" < "$vf" > "$run_dir/validator_$(basename "$vf").out"; then
        validator_failed=1
        break
      fi
    done
  fi
  [[ "$validator_failed" -eq 0 ]] || bk_fail "Falló un validator SQL"

  stage="retention"
  bk_log "Retención"
  find "$base_dir" -mindepth 1 -maxdepth 1 -type d -printf '%P\n' | sort -r | awk -v keep="$daily_keep" 'NR>keep {print}' | while read -r old; do
    [[ -n "$old" ]] && rm -rf "$base_dir/$old"
  done

  stage="report"
  ended_at="$(date +%s)"
  duration_sec=$((ended_at - started_at))
  size_bytes="$(stat -c %s "$dump_gz")"
  size_h="$(du -h "$dump_gz" | awk '{print $1}')"

  cat > "$report_json" <<JSON
{
  "status": "OK",
  "project": "$project_name",
  "resource": "mysql/$MYSQL_DATABASE",
  "started_at": "$started_at",
  "ended_at": "$ended_at",
  "duration_sec": $duration_sec,
  "artifact": "$dump_gz",
  "artifact_size_bytes": $size_bytes,
  "artifact_size_human": "$size_h",
  "sha256_short": "$sha_short",
  "restore_test": "OK",
  "warnings": 0
}
JSON

  msg=$(cat <<MSG
✅ Backup OK
Proyecto: $project_name
Recurso: mysql/$MYSQL_DATABASE
Fecha: $(bk_now_iso)
Duración: ${duration_sec}s
Tamaño: $size_h
SHA256: ${sha_short}...
Restore: OK
Warnings: 0
Archivo: $(basename "$dump_gz")
MSG
)
  printf '%s\n' "$msg"

  if [[ "$telegram_enabled" == "true" ]]; then
    send_telegram "$policy_json" "$msg" || bk_log "WARN: falló Telegram"
  fi

  mysql --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" -e "DROP DATABASE IF EXISTS \`$restore_db\`;"
  trap - EXIT
  rm -f "$policy_json" "$full_tmp" "$schema_tmp"
}

send_telegram() {
  local policy_json="$1"
  local msg="$2"
  local token chat_id
  token="${TELEGRAM_BOT_TOKEN:-}"
  chat_id="${TELEGRAM_CHAT_ID:-}"
  [[ -n "$token" && -n "$chat_id" ]] || return 1
  curl -fsS -X POST "https://api.telegram.org/bot${token}/sendMessage" \
    -d "chat_id=$chat_id" \
    --data-urlencode "text=$msg" >/dev/null
}
