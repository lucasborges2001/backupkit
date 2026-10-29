from adapters.mysql.adapter import MySQLAdapter
from adapters.filesystem.adapter import FilesystemAdapter
from adapters.influxdb2.adapter import InfluxDB2Adapter

ADAPTERS = {
    'mysql': MySQLAdapter,
    'filesystem': FilesystemAdapter,
    'influxdb2': InfluxDB2Adapter,
}
