"""SQLite-backed sessions and jobs; payloads stay in bounded runtime directories."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


def env_bool(name: str, default: str) -> bool:
    value = os.environ.get(name, default).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        # Name only: a configuration value never reaches a log line.
        raise ValueError(f"{name} must be an integer") from None


def running_under_systemd() -> bool:
    # systemd sets INVOCATION_ID for every process it starts for a unit.
    return bool(os.environ.get("INVOCATION_ID"))


def explicit_path(name: str) -> Path:
    raw = os.environ.get(name, "").strip()
    path = Path(raw)
    if not raw or not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{name} must be an explicit absolute path when running under systemd")
    return path


@dataclass(frozen=True)
class LiveSettings:
    runtime_root: Path
    database_path: Path
    max_sessions: int = 10
    idle_seconds: int = 180
    absolute_seconds: int = 1800
    lease_seconds: int = 180
    max_attempts: int = 3
    max_claimed_jobs: int = 1
    max_upload_bytes: int = 2 * 1024**3
    max_expanded_bytes: int = 8 * 1024**3
    max_result_bytes: int = 2 * 1024**3
    cookie_secure: bool = True

    def __post_init__(self):
        if not 1 <= self.max_sessions <= 100:
            raise ValueError("MERGEN_MAX_ACTIVE_SESSIONS must be between 1 and 100")
        if not 60 <= self.idle_seconds < self.absolute_seconds <= 86400:
            raise ValueError("session time limits are invalid")
        if not 30 <= self.lease_seconds <= 3600 or not 1 <= self.max_attempts <= 10:
            raise ValueError("worker lease settings are invalid")
        if not 1 <= self.max_claimed_jobs <= 10:
            raise ValueError("MERGEN_MAX_CLAIMED_JOBS must be between 1 and 10")
        if min(self.max_upload_bytes, self.max_expanded_bytes, self.max_result_bytes) <= 0:
            raise ValueError("file size limits must be positive")

    @classmethod
    def from_env(cls) -> "LiveSettings":
        if running_under_systemd():
            # A service never guesses where live uploads go. The checkout-
            # relative default below is for local development only; under
            # systemd a missing value is a configuration error, not a fallback.
            root = explicit_path("MERGEN_RUNTIME_ROOT")
            database = explicit_path("MERGEN_DATABASE_PATH")
            if not database.is_relative_to(root):
                raise ValueError("MERGEN_DATABASE_PATH must be inside MERGEN_RUNTIME_ROOT")
            root, database = root.resolve(), database.resolve()
        else:
            root = Path(os.environ.get("MERGEN_RUNTIME_ROOT", ".local/runtime")).resolve()
            database = Path(os.environ.get("MERGEN_DATABASE_PATH", root / "control.sqlite3")).resolve()
        return cls(
            runtime_root=root,
            database_path=database,
            max_sessions=env_int("MERGEN_MAX_ACTIVE_SESSIONS", 10),
            idle_seconds=env_int("MERGEN_SESSION_IDLE_SECONDS", 180),
            absolute_seconds=env_int("MERGEN_SESSION_MAX_SECONDS", 1800),
            lease_seconds=env_int("MERGEN_WORKER_LEASE_SECONDS", 180),
            max_attempts=env_int("MERGEN_JOB_MAX_ATTEMPTS", 3),
            max_claimed_jobs=env_int("MERGEN_MAX_CLAIMED_JOBS", 1),
            max_upload_bytes=env_int("MERGEN_MAX_UPLOAD_BYTES", 2 * 1024**3),
            max_expanded_bytes=env_int("MERGEN_MAX_EXPANDED_BYTES", 8 * 1024**3),
            max_result_bytes=env_int("MERGEN_MAX_RESULT_BYTES", 2 * 1024**3),
            cookie_secure=env_bool("MERGEN_COOKIE_SECURE", "true"),
        )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class CapacityError(Exception):
    pass


class LiveStore:
    def __init__(self, settings: LiveSettings):
        self.settings = settings
        settings.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        settings.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.settings.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA secure_delete=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self):
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    token_hash TEXT UNIQUE NOT NULL,
                    csrf_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    absolute_expires INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    module TEXT NOT NULL CHECK(module IN ('imaging','genomics')),
                    disease TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued','claimed','running','completed','failed','cancelled')),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    claimed_by TEXT,
                    lease_until INTEGER,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    input_sha256 TEXT NOT NULL,
                    result_sha256 TEXT,
                    result_manifest TEXT,
                    error_code TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS one_open_job_per_session
                    ON jobs(session_id) WHERE status IN ('queued','claimed','running');
                CREATE TABLE IF NOT EXISTS workers (
                    id TEXT PRIMARY KEY,
                    capabilities TEXT NOT NULL,
                    last_seen INTEGER NOT NULL
                );
            """)

    @staticmethod
    def now() -> int:
        return int(time.time())

    def session_directory(self, session_id: str) -> Path:
        path = (self.settings.runtime_root / "sessions" / session_id).resolve()
        base = (self.settings.runtime_root / "sessions").resolve()
        if not path.is_relative_to(base):
            raise ValueError("invalid session path")
        return path

    def job_directory(self, session_id: str, job_id: str) -> Path:
        return self.session_directory(session_id) / "jobs" / job_id

    def create_session(self):
        now = self.now()
        session_id, token, csrf = secrets.token_hex(16), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute(
                "SELECT COUNT(*) FROM sessions WHERE last_seen>? AND absolute_expires>?",
                (now - self.settings.idle_seconds, now),
            ).fetchone()[0]
            if active >= self.settings.max_sessions:
                raise CapacityError
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
                (session_id, digest(token), digest(csrf), now, now, now + self.settings.absolute_seconds),
            )
        self.session_directory(session_id).mkdir(parents=True, mode=0o700)
        return {"id": session_id, "token": token, "csrf": csrf, "created_at": now,
                "absolute_expires": now + self.settings.absolute_seconds}

    def get_session(self, token: str | None):
        if not token:
            return None
        now = self.now()
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE token_hash=?", (digest(token),)).fetchone()
        if not row or row["last_seen"] <= now - self.settings.idle_seconds or row["absolute_expires"] <= now:
            if row:
                self.delete_session(row["id"])
            return None
        return dict(row)

    def validate_csrf(self, session: dict, cookie: str | None, header: str | None) -> bool:
        return bool(cookie and header and secrets.compare_digest(cookie, header)
                    and secrets.compare_digest(session["csrf_hash"], digest(header)))

    def heartbeat(self, session_id: str):
        now = self.now()
        with self.connect() as db:
            db.execute("UPDATE sessions SET last_seen=? WHERE id=?", (now, session_id))
        return now

    def delete_session(self, session_id: str):
        directory = self.session_directory(session_id)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        shutil.rmtree(directory, ignore_errors=True)

    def create_job(self, session_id: str, module: str, disease: str, input_sha256: str,
                   job_id: str | None = None):
        job_id, now = job_id or secrets.token_hex(16), self.now()
        with self.connect() as db:
            try:
                db.execute(
                    "INSERT INTO jobs(id,session_id,module,disease,status,created_at,updated_at,input_sha256) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (job_id, session_id, module, disease, "queued", now, now, input_sha256),
                )
            except sqlite3.IntegrityError as exc:
                raise CapacityError from exc
        return job_id

    def job_for_session(self, job_id: str, session_id: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND session_id=?", (job_id, session_id)).fetchone()
        return dict(row) if row else None

    def claim(self, worker_id: str, capabilities: list[str]):
        if not capabilities:
            return None
        now = self.now()
        placeholders = ",".join("?" for _ in capabilities)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            running = db.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('claimed','running')"
            ).fetchone()[0]
            if running >= self.settings.max_claimed_jobs:
                return None
            row = db.execute(
                f"SELECT j.* FROM jobs j JOIN sessions s ON s.id=j.session_id "
                f"WHERE j.status='queued' AND j.module IN ({placeholders}) "
                "AND s.last_seen>? AND s.absolute_expires>? ORDER BY j.created_at LIMIT 1",
                (*capabilities, now - self.settings.idle_seconds, now),
            ).fetchone()
            if not row:
                return None
            changed = db.execute(
                "UPDATE jobs SET status='claimed',claimed_by=?,lease_until=?,attempts=attempts+1,updated_at=? "
                "WHERE id=? AND status='queued'",
                (worker_id, now + self.settings.lease_seconds, now, row["id"]),
            ).rowcount
            if changed != 1:
                return None
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def touch_worker(self, worker_id: str, capabilities: list[str]):
        with self.connect() as db:
            db.execute(
                "INSERT INTO workers(id,capabilities,last_seen) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET capabilities=excluded.capabilities,last_seen=excluded.last_seen",
                (worker_id, json.dumps(sorted(capabilities), separators=(",", ":")), self.now()),
            )

    def available_capabilities(self, max_age: int = 90):
        cutoff = self.now() - max_age
        capabilities: set[str] = set()
        with self.connect() as db:
            for row in db.execute("SELECT capabilities FROM workers WHERE last_seen>?", (cutoff,)):
                capabilities.update(json.loads(row["capabilities"]))
        return sorted(capabilities)

    def worker_job(self, job_id: str, worker_id: str):
        now = self.now()
        with self.connect() as db:
            row = db.execute(
                "SELECT j.* FROM jobs j JOIN sessions s ON s.id=j.session_id "
                "WHERE j.id=? AND j.claimed_by=? AND s.last_seen>? AND s.absolute_expires>?",
                (job_id, worker_id, now - self.settings.idle_seconds, now),
            ).fetchone()
        return dict(row) if row else None

    def renew_lease(self, job_id: str, worker_id: str):
        now = self.now()
        with self.connect() as db:
            changed = db.execute(
                "UPDATE jobs SET status='running',lease_until=?,updated_at=? "
                "WHERE id=? AND claimed_by=? AND status IN ('claimed','running') AND lease_until>? "
                "AND EXISTS(SELECT 1 FROM sessions s WHERE s.id=jobs.session_id AND s.last_seen>? AND s.absolute_expires>?)",
                (now + self.settings.lease_seconds, now, job_id, worker_id, now,
                 now - self.settings.idle_seconds, now),
            ).rowcount
        return changed == 1

    def complete(self, job_id: str, worker_id: str, result_sha256: str, manifest: dict):
        now = self.now()
        with self.connect() as db:
            changed = db.execute(
                "UPDATE jobs SET status='completed',result_sha256=?,result_manifest=?,lease_until=NULL,updated_at=? "
                "WHERE id=? AND claimed_by=? AND status IN ('claimed','running') AND lease_until>? "
                "AND EXISTS(SELECT 1 FROM sessions s WHERE s.id=jobs.session_id AND s.last_seen>? AND s.absolute_expires>?)",
                (result_sha256, json.dumps(manifest, separators=(",", ":")), now,
                 job_id, worker_id, now, now - self.settings.idle_seconds, now),
            ).rowcount
        return changed == 1

    def fail(self, job_id: str, worker_id: str, error_code: str):
        with self.connect() as db:
            changed = db.execute(
                "UPDATE jobs SET status='failed',error_code=?,lease_until=NULL,updated_at=? "
                "WHERE id=? AND claimed_by=? AND status IN ('claimed','running')",
                (error_code, self.now(), job_id, worker_id),
            ).rowcount
        return changed == 1

    def cleanup(self):
        now = self.now()
        with self.connect() as db:
            expired = [row[0] for row in db.execute(
                "SELECT id FROM sessions WHERE last_seen<=? OR absolute_expires<=?",
                (now - self.settings.idle_seconds, now),
            )]
            stale = list(db.execute(
                "SELECT id,session_id,attempts FROM jobs WHERE status IN ('claimed','running') AND lease_until<=?", (now,)
            ))
            for row in stale:
                if row["attempts"] >= self.settings.max_attempts:
                    db.execute("UPDATE jobs SET status='failed',error_code='worker-timeout',updated_at=? WHERE id=?",
                               (now, row["id"]))
                else:
                    db.execute("UPDATE jobs SET status='queued',claimed_by=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                               (now, row["id"]))
            db.execute("DELETE FROM workers WHERE last_seen<=?", (now - 86400,))
        for session_id in expired:
            self.delete_session(session_id)
        for row in stale:
            (self.job_directory(row["session_id"], row["id"]) / "result.part").unlink(missing_ok=True)
        return {"expiredSessions": len(expired), "staleJobs": len(stale)}
