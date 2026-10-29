from adapters.mysql.adapter import MySQLAdapter
from adapters.filesystem.adapter import FilesystemAdapter

ADAPTERS = {
    'mysql': MySQLAdapter,
    'filesystem': FilesystemAdapter,
}
