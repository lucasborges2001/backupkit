from __future__ import annotations

import os
import subprocess

from core.config import deep_get
from core.precheck import tcp_connectivity
from core.result import CheckResult
from core.tools import resolve_tool


class MySQLAdapter:
    name = 'mysql'

    @staticmethod
    def run_prechecks(config: dict, report):
        policy = config['policy']
        env = config['env']
        host = deep_get(policy, 'resource.connection.host')
        port = int(deep_get(policy, 'resource.connection.port', 3306))
        database = deep_get(policy, 'resource.connection.database')
        username = deep_get(policy, 'resource.connection.username')
        timeout = int(deep_get(policy, 'prechecks.connectivity_timeout_sec', 5))
        password = env.get('MYSQL_PASSWORD', '')

        try:
            tcp_connectivity(host, port, timeout)
            report.add(CheckResult('adapter.mysql.connectivity', 'OK', 'blocking', f'MySQL reachable at {host}:{port}'))
        except Exception as exc:
            report.add(CheckResult('adapter.mysql.connectivity', 'ERROR', 'blocking', f'MySQL not reachable at {host}:{port}: {exc}'))
            return

        mysql_bin = resolve_tool('mysql_query_client') or 'mysql'
        env_vars = os.environ.copy()
        if password:
            env_vars['MYSQL_PWD'] = password
        cmd = [mysql_bin, '-h', host, '-P', str(port), '-u', username, '-D', database, '-e', 'SELECT 1;']
        try:
            completed = subprocess.run(cmd, env=env_vars, capture_output=True, text=True, timeout=max(5, timeout))
            if completed.returncode != 0:
                stderr = (completed.stderr or completed.stdout or '').strip()
                report.add(CheckResult('adapter.mysql.auth', 'ERROR', 'blocking', f'MySQL auth/query failed: {stderr}'))
            else:
                report.add(CheckResult('adapter.mysql.auth', 'OK', 'blocking', 'MySQL auth and database query succeeded'))
        except Exception as exc:
            report.add(CheckResult('adapter.mysql.auth', 'ERROR', 'blocking', f'MySQL auth check failed: {exc}'))
