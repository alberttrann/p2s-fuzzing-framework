"""
P2S State Adapters: Handles target environment snapshotting and restoration.
Supports PostgreSQL (with optional initial SQL seeding & post-seed alignment),
MongoDB, File DBs, Docker, and Stateless modes.
"""
from abc import ABC, abstractmethod
import subprocess
import time
import shutil
import os

class BaseStateAdapter(ABC):
    @abstractmethod
    def create_snapshot(self) -> None: pass
    @abstractmethod
    def restore_snapshot(self) -> None: pass


class PostgresTemplateAdapter(BaseStateAdapter):
    """Sub-second state reset for PostgreSQL using CREATE DATABASE WITH TEMPLATE."""

    def __init__(self, active_db: str, template_db: str, admin_uri: str,
                 seed_command: str = None, pre_snapshot_hook: callable = None):
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
        self.active_db = active_db
        self.template_db = template_db
        self.admin_uri = admin_uri
        self.seed_command = seed_command
        self.pre_snapshot_hook = pre_snapshot_hook
        self.psycopg2 = psycopg2
        self.iso_level = ISOLATION_LEVEL_AUTOCOMMIT

    def _execute_sql(self, query: str, db_name: str = None):
        uri = self.admin_uri if not db_name else f"{self.admin_uri.rsplit('/', 1)[0]}/{db_name}"
        conn = self.psycopg2.connect(uri)
        conn.set_isolation_level(self.iso_level)
        with conn.cursor() as cur:
            try: cur.execute(query)
            except Exception: pass
        conn.close()

    def _terminate_connections(self, db_name: str):
        self._execute_sql(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname='{db_name}' AND pid<>pg_backend_pid();"
        )

    def create_snapshot(self):
        # Auto-seed if template_db does not exist yet
        if not self._db_exists(self.template_db):
            if self.seed_command:
                print(f"[*] Seeding active database '{self.active_db}' before first snapshot...")
                subprocess.run(self.seed_command, shell=True, check=True)
            if self.pre_snapshot_hook:
                print(f"[*] Executing pre-snapshot hook...")
                self.pre_snapshot_hook(self.active_db)

        self._execute_sql(f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = false;")
        self._terminate_connections(self.active_db)
        self._execute_sql(f"DROP DATABASE IF EXISTS {self.template_db};")

        snapped = False
        for _ in range(5):
            try:
                self._execute_sql(
                    f"CREATE DATABASE {self.template_db} WITH TEMPLATE {self.active_db};"
                )
                snapped = True
                break
            except Exception:
                time.sleep(0.2)
                self._terminate_connections(self.active_db)

        self._execute_sql(f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = true;")
        if not snapped:
            raise RuntimeError("Database snapshot creation failed after 5 attempts.")

    def restore_snapshot(self):
        try:
            self._execute_sql(f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = false;")
            self._terminate_connections(self.active_db)

            restored = False
            for _ in range(5):
                try:
                    self._execute_sql(f"DROP DATABASE IF EXISTS {self.active_db};")
                    self._execute_sql(
                        f"CREATE DATABASE {self.active_db} WITH TEMPLATE {self.template_db};"
                    )
                    restored = True
                    break
                except Exception:
                    time.sleep(0.2)
                    self._terminate_connections(self.active_db)

            if not restored:
                raise RuntimeError("Database restore failed after 5 attempts.")
        finally:
            self._execute_sql(f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = true;")
            time.sleep(1.0)

    def _db_exists(self, db_name: str) -> bool:
        conn = self.psycopg2.connect(self.admin_uri)
        conn.set_isolation_level(self.iso_level)
        with conn.cursor() as cur:
            cur.execute(f"SELECT 1 FROM pg_database WHERE datname='{db_name}';")
            exists = cur.fetchone() is not None
        conn.close()
        return exists


class MongoDumpAdapter(BaseStateAdapter):
    def __init__(self, db_name: str, mongo_uri: str, dump_dir: str = "/tmp/p2s_mongo_snap"):
        self.db_name = db_name
        self.mongo_uri = mongo_uri
        self.dump_dir = dump_dir

    def create_snapshot(self):
        if os.path.exists(self.dump_dir): shutil.rmtree(self.dump_dir)
        subprocess.run(
            ["mongodump", "--uri", self.mongo_uri, "-d", self.db_name, "-o", self.dump_dir],
            check=True, stdout=subprocess.DEVNULL
        )

    def restore_snapshot(self):
        dump_path = os.path.join(self.dump_dir, self.db_name)
        subprocess.run(
            ["mongorestore", "--uri", self.mongo_uri, "--drop", "-d", self.db_name, dump_path],
            check=True, stdout=subprocess.DEVNULL
        )


class FileBackupAdapter(BaseStateAdapter):
    def __init__(self, active_file_path: str, backup_file_path: str):
        self.active = active_file_path
        self.backup = backup_file_path

    def create_snapshot(self): shutil.copy2(self.active, self.backup)
    def restore_snapshot(self): shutil.copy2(self.backup, self.active)


class DockerRestartAdapter(BaseStateAdapter):
    def __init__(self, container_name: str, sleep_time: float = 2.0):
        self.container_name = container_name
        self.sleep_time = sleep_time

    def create_snapshot(self): pass

    def restore_snapshot(self):
        subprocess.run(
            ["docker", "restart", self.container_name],
            check=True, stdout=subprocess.DEVNULL
        )
        time.sleep(self.sleep_time)


class StatelessAdapter(BaseStateAdapter):
    def create_snapshot(self): pass
    def restore_snapshot(self): pass
