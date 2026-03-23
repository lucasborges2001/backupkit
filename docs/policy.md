# policy.yml soportada en este starter

```yml
project:
  name: mysql-basic
backup:
  out_dir: ./out
mysql:
  exclude_tables:
    - logs
  schema_only_tables:
    - audit_events
  restore_test_db_prefix: bk_restore
validators:
  sql_files:
    - ./backup/validators/00_smoke.sql
retention:
  daily_keep: 7
notifications:
  telegram:
    enabled: false
```
