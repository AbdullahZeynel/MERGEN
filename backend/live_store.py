"""SQLite-backed sessions and jobs; payloads stay in bounded runtime directories."""
from __future__ import annotations

import hashlib
import json
import os
import re
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
    orphan_grace_seconds: int = 3600
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
        if not 60 <= self.orphan_grace_seconds <= 86400:
            raise ValueError("MERGEN_ORPHAN_GRACE_SECONDS must be between 60 and 86400")

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
            orphan_grace_seconds=env_int("MERGEN_ORPHAN_GRACE_SECONDS", 3600),
            cookie_secure=env_bool("MERGEN_COOKIE_SECURE", "true"),
        )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class CapacityError(Exception):
    pass


SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
UPLOAD_PART = re.compile(r"^upload-[0-9a-f]{16}\.part$")


class LiveStore:
    def __init__(self, settings: LiveSettings):
        self.settings = settings
        settings.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        settings.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._initialize()
        self._recover_session_deletions()
        self._quarantine_orphans()

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
                    module TEXT NOT NULL CHECK(module = 'imaging'),
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

    @property
    def session_trash(self) -> Path:
        return self.settings.runtime_root / ".trash" / "sessions"

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _recover_session_deletions(self) -> None:
        """Finish or roll back only tombstones created by delete_session()."""
        self.session_trash.mkdir(parents=True, exist_ok=True, mode=0o700)
        sessions_root = self.settings.runtime_root / "sessions"
        sessions_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            existing = {row[0] for row in db.execute("SELECT id FROM sessions")}
        for tombstone in self.session_trash.iterdir():
            try:
                is_directory = tombstone.is_dir() and not tombstone.is_symlink()
            except OSError:
                continue
            if not SESSION_ID.fullmatch(tombstone.name) or not is_directory:
                continue
            live = self.session_directory(tombstone.name)
            if tombstone.name in existing:
                if not live.exists() and not live.is_symlink():
                    tombstone.replace(live)
                    self._fsync_directory(sessions_root)
                    self._fsync_directory(self.session_trash)
            else:
                try:
                    shutil.rmtree(tombstone)
                    self._fsync_directory(self.session_trash)
                except OSError:
                    # The next process start or cleanup run can retry. The
                    # payload remains outside the live session namespace.
                    pass

    def _quarantine_orphans(self) -> None:
        """Move protocol-owned leftovers out of the live namespace.

        Quarantine is intentionally recoverable: unknown names are untouched
        and this routine never deletes quarantined payloads.
        """
        sessions_root = self.settings.runtime_root / "sessions"
        quarantine = self.settings.runtime_root / ".quarantine"
        targets = {kind: quarantine / kind for kind in ("sessions", "uploads", "jobs")}
        for target in targets.values():
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            session_ids = {row[0] for row in db.execute("SELECT id FROM sessions")}
            job_ids = {(row[0], row[1]) for row in db.execute("SELECT session_id,id FROM jobs")}
        cutoff = self.now() - self.settings.orphan_grace_seconds

        def old_enough(path: Path) -> bool:
            try:
                return path.stat(follow_symlinks=False).st_mtime <= cutoff
            except OSError:
                return False

        for session_entry in sessions_root.iterdir():
            if (not SESSION_ID.fullmatch(session_entry.name) or session_entry.is_symlink()
                    or not session_entry.is_dir()):
                continue
            session_id = session_entry.name
            if session_id not in session_ids:
                target = targets["sessions"] / session_id
                if old_enough(session_entry) and not target.exists() and not target.is_symlink():
                    session_entry.replace(target)
                    self._fsync_directory(sessions_root)
                    self._fsync_directory(targets["sessions"])
                continue

            for partial in session_entry.iterdir():
                if not UPLOAD_PART.fullmatch(partial.name) or not old_enough(partial):
                    continue
                target = targets["uploads"] / f"{session_id}-{partial.name[7:-5]}"
                if not target.exists() and not target.is_symlink():
                    partial.replace(target)
                    self._fsync_directory(session_entry)
                    self._fsync_directory(targets["uploads"])

            jobs_root = session_entry / "jobs"
            if not jobs_root.is_dir() or jobs_root.is_symlink():
                continue
            for job_entry in jobs_root.iterdir():
                if (not SESSION_ID.fullmatch(job_entry.name) or job_entry.is_symlink()
                        or not job_entry.is_dir() or (session_id, job_entry.name) in job_ids
                        or not old_enough(job_entry)):
                    continue
                target = targets["jobs"] / f"{session_id}-{job_entry.name}"
                if not target.exists() and not target.is_symlink():
                    job_entry.replace(target)
                    self._fsync_directory(jobs_root)
                    self._fsync_directory(targets["jobs"])

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
            # The minute timer owns filesystem deletion. Authentication stays
            # read-only so an expired-cookie request cannot block the API event
            # loop while a potentially large session tree is removed.
            return None
        return dict(row)

    def validate_csrf(self, session: dict, cookie: str | None, header: str | None) -> bool:
        return bool(cookie and header and secrets.compare_digest(cookie, header)
                    and secrets.compare_digest(session["csrf_hash"], digest(header)))

    def heartbeat(self, session_id: str):
        now = self.now()
        with self.connect() as db:
            changed = db.execute(
                "UPDATE sessions SET last_seen=? WHERE id=? AND absolute_expires>?",
                (now, session_id, now),
            ).rowcount
        return now if changed == 1 else None

    def delete_session(self, session_id: str, *, expired_before: int | None = None) -> bool:
        directory = self.session_directory(session_id)
        self.session_trash.mkdir(parents=True, exist_ok=True, mode=0o700)
        tombstone = self.session_trash / session_id
        moved = False
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT last_seen,absolute_expires FROM sessions WHERE id=?", (session_id,)
                ).fetchone()
                if not row:
                    return False
                if expired_before is not None and not (
                    row["last_seen"] <= expired_before - self.settings.idle_seconds
                    or row["absolute_expires"] <= expired_before
                ):
                    return False
                if tombstone.exists() or tombstone.is_symlink():
                    raise OSError("session deletion is already pending recovery")
                if directory.exists() and not directory.is_symlink():
                    directory.replace(tombstone)
                    moved = True
                    self._fsync_directory(directory.parent)
                    self._fsync_directory(self.session_trash)
                db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        except BaseException:
            if moved and not directory.exists() and not directory.is_symlink():
                tombstone.replace(directory)
                self._fsync_directory(directory.parent)
                self._fsync_directory(self.session_trash)
            raise
        if moved:
            try:
                shutil.rmtree(tombstone)
                self._fsync_directory(self.session_trash)
            except OSError:
                pass
        return True

    def create_job(self, session_id: str, module: str, disease: str, input_sha256: str,
                   job_id: str | None = None):
        if module != "imaging" or disease != "glioma":
            raise ValueError("unsupported live analysis profile")
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

    def publish_job_input(self, session_id: str, module: str, disease: str,
                          input_sha256: str, staging: Path, job_id: str) -> str:
        """Publish input.zip and its queue row under one SQLite write lock.

        A claimant cannot observe the row until the input rename is durable. If
        a normal exception occurs, the upload is moved back for the caller's
        finally cleanup; a process crash is handled by orphan quarantine.
        """
        if module != "imaging" or disease != "glioma":
            raise ValueError("unsupported live analysis profile")
        now = self.now()
        job_directory = self.job_directory(session_id, job_id)
        destination = job_directory / "input.zip"
        moved = False
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    db.execute(
                        "INSERT INTO jobs(id,session_id,module,disease,status,created_at,updated_at,input_sha256) "
                        "VALUES(?,?,?,?,?,?,?,?)",
                        (job_id, session_id, module, disease, "queued", now, now, input_sha256),
                    )
                except sqlite3.IntegrityError as exc:
                    raise CapacityError from exc
                destination.parent.mkdir(parents=True, exist_ok=False, mode=0o700)
                staging.replace(destination)
                moved = True
                with destination.open("rb") as uploaded:
                    os.fsync(uploaded.fileno())
                self._fsync_directory(job_directory)
                self._fsync_directory(job_directory.parent)
        except BaseException:
            if moved and destination.exists() and not staging.exists():
                destination.replace(staging)
            shutil.rmtree(job_directory, ignore_errors=True)
            raise
        return job_id

    def job_for_session(self, job_id: str, session_id: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND session_id=?", (job_id, session_id)).fetchone()
        return dict(row) if row else None

    def claim(self, worker_id: str, capabilities: list[str]):
        if capabilities != ["imaging"]:
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
        now = self.now()
        with self.connect() as db:
            changed = db.execute(
                "UPDATE jobs SET status='failed',error_code=?,lease_until=NULL,updated_at=? "
                "WHERE id=? AND claimed_by=? AND status IN ('claimed','running') AND lease_until>? "
                "AND EXISTS(SELECT 1 FROM sessions s WHERE s.id=jobs.session_id AND s.last_seen>? AND s.absolute_expires>?)",
                (error_code, now, job_id, worker_id, now,
                 now - self.settings.idle_seconds, now),
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
                # A new claim cannot create another result.part while this
                # write transaction is held.
                (self.job_directory(row["session_id"], row["id"]) / "result.part").unlink(missing_ok=True)
            db.execute("DELETE FROM workers WHERE last_seen<=?", (now - 86400,))
        removed = 0
        for session_id in expired:
            removed += self.delete_session(session_id, expired_before=now)
        return {"expiredSessions": removed, "staleJobs": len(stale)}
