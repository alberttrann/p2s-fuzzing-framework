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

from ...research.shell import run_shell

class BaseStateAdapter(ABC):
    @abstractmethod
    def create_snapshot(self) -> None: pass
    @abstractmethod
    def restore_snapshot(self) -> None: pass

    def reset_baseline(self) -> None:
        """Reset the target to its seed/baseline state when supported.

        The default falls back to ``restore_snapshot``.  Stateful adapters that
        can recreate a canonical seed (notably PostgreSQL) override this method.
        """
        self.restore_snapshot()


class PostgresTemplateAdapter(BaseStateAdapter):
    """Fast PostgreSQL reset using ``CREATE DATABASE ... WITH TEMPLATE``.

    v1.2 also supports an explicit seed-baseline recreation.  This lets the
    shared fuzzer reproduce Track-A's per-flow fresh database initialisation
    without embedding SEAL/AITasker code in the engine.
    """

    def __init__(self, active_db: str, template_db: str, admin_uri: str,
                 seed_command: str = None, pre_snapshot_hook: callable = None,
                 working_directory: str = "",
                 recreate_active_before_seed: bool = False,
                 post_seed_commands: list[str] | None = None):
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
        self.active_db = active_db
        self.template_db = template_db
        self.admin_uri = admin_uri
        self.seed_command = seed_command
        self.pre_snapshot_hook = pre_snapshot_hook
        self.working_directory = working_directory or None
        self.recreate_active_before_seed = bool(recreate_active_before_seed)
        self.post_seed_commands = list(post_seed_commands or [])
        self.psycopg2 = psycopg2
        self.iso_level = ISOLATION_LEVEL_AUTOCOMMIT
        self._baseline_ready = False

    def _execute_sql(self, query: str, db_name: str = None, *, ignore_errors: bool = False):
        uri = self.admin_uri if not db_name else f"{self.admin_uri.rsplit('/', 1)[0]}/{db_name}"
        conn = self.psycopg2.connect(uri)
        conn.set_isolation_level(self.iso_level)
        try:
            with conn.cursor() as cur:
                cur.execute(query)
        except Exception:
            if not ignore_errors:
                raise
        finally:
            conn.close()

    def _terminate_connections(self, db_name: str):
        self._execute_sql(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname='{db_name}' AND pid<>pg_backend_pid();",
            ignore_errors=True,
        )

    def _run_shell(self, command: str):
        if command and command.strip():
            run_shell(command, check=True, cwd=self.working_directory or None)

    def reset_baseline(self):
        if self.recreate_active_before_seed:
            self._terminate_connections(self.active_db)
            self._execute_sql(f"DROP DATABASE IF EXISTS {self.active_db};")
            self._execute_sql(f"CREATE DATABASE {self.active_db};")
        if self.seed_command:
            print(f"[*] Seeding active database '{self.active_db}'...")
            self._run_shell(self.seed_command)
        for command in self.post_seed_commands:
            print(f"[*] Post-seed setup: {command}")
            self._run_shell(command)
        if self.pre_snapshot_hook:
            print("[*] Executing pre-snapshot hook...")
            self.pre_snapshot_hook(self.active_db)
        self._baseline_ready = True

    def create_snapshot(self):
        # First use of an adapter always establishes a canonical seed if a seed
        # path is configured.  Later per-flow reseeds are driven explicitly by
        # the fuzzer's reset_before_each_flow option.
        if not self._db_exists(self.template_db) and not self._baseline_ready:
            if self.seed_command or self.pre_snapshot_hook or self.post_seed_commands:
                self.reset_baseline()

        self._execute_sql(
            f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = false;",
            ignore_errors=True,
        )
        self._terminate_connections(self.active_db)
        self._execute_sql(f"DROP DATABASE IF EXISTS {self.template_db};")

        snapped = False
        last_error = None
        for _ in range(5):
            try:
                self._execute_sql(
                    f"CREATE DATABASE {self.template_db} WITH TEMPLATE {self.active_db};"
                )
                snapped = True
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.2)
                self._terminate_connections(self.active_db)

        self._execute_sql(
            f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = true;",
            ignore_errors=True,
        )
        if not snapped:
            raise RuntimeError(
                f"Database snapshot creation failed after 5 attempts: {last_error}"
            )

    def restore_snapshot(self):
        try:
            self._execute_sql(
                f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = false;",
                ignore_errors=True,
            )
            self._terminate_connections(self.active_db)

            restored = False
            last_error = None
            for _ in range(5):
                try:
                    self._execute_sql(f"DROP DATABASE IF EXISTS {self.active_db};")
                    self._execute_sql(
                        f"CREATE DATABASE {self.active_db} WITH TEMPLATE {self.template_db};"
                    )
                    restored = True
                    break
                except Exception as exc:
                    last_error = exc
                    time.sleep(0.2)
                    self._terminate_connections(self.active_db)

            if not restored:
                raise RuntimeError(
                    f"Database restore failed after 5 attempts: {last_error}"
                )
        finally:
            self._execute_sql(
                f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = true;",
                ignore_errors=True,
            )
            time.sleep(1.0)

    def _db_exists(self, db_name: str) -> bool:
        conn = self.psycopg2.connect(self.admin_uri)
        conn.set_isolation_level(self.iso_level)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname=%s;", (db_name,))
                return cur.fetchone() is not None
        finally:
            conn.close()


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


class CommandStateAdapter(BaseStateAdapter):
    """State adapter backed by configured shell commands.

    This is the framework-native escape hatch used by the heterogeneous
    RESTgym targets.  It keeps target reset logic in TOML instead of in a
    forked evaluator: SQL reseeds, Ganache contract redeployments, MongoDB
    drop/reseed commands, Kafka topic recreation, and container restarts can
    all be represented without changing the P2S engine.
    """

    def __init__(self, create_command: str = "", restore_command: str = "",
                 working_directory: str = "", restore_sleep_seconds: float = 0.0):
        self.create_command = create_command or ""
        self.restore_command = restore_command or ""
        self.working_directory = working_directory or None
        self.restore_sleep_seconds = float(restore_sleep_seconds or 0.0)

    def _run(self, command: str):
        if not command:
            return
        run_shell(
            command, check=True, cwd=self.working_directory or None,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def create_snapshot(self):
        self._run(self.create_command)

    def restore_snapshot(self):
        self._run(self.restore_command)
        if self.restore_sleep_seconds > 0:
            time.sleep(self.restore_sleep_seconds)


class StatelessAdapter(BaseStateAdapter):
    def create_snapshot(self): pass
    def restore_snapshot(self): pass
