from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from datetime import datetime, timezone

VALID_TRANSITIONS = {
    "RESERVED": {"READY_TO_UPLOAD"},
    "READY_TO_UPLOAD": {"PREVIEW_UPLOADING", "ORIGINAL_UPLOADING"},
    "PREVIEW_UPLOADING": {"PREVIEW_CONFIRMED", "NEEDS_REVIEW", "RETRY_WAIT", "CONFIGURATION_ERROR"},
    "PREVIEW_CONFIRMED": {"ORIGINAL_UPLOADING"},
    "ORIGINAL_UPLOADING": {"BACKED_UP", "NEEDS_REVIEW", "RETRY_WAIT", "CONFIGURATION_ERROR"},
    "RETRY_WAIT": {"PREVIEW_UPLOADING", "ORIGINAL_UPLOADING"},
    "NEEDS_REVIEW": set(),
    "CONFIGURATION_ERROR": {"READY_TO_UPLOAD", "PREVIEW_CONFIRMED"}, # Manual fix required
    "BACKED_UP": set()
}

class ArchiveDatabase:
    def __init__(self, path: Path, read_only: bool = False) -> None:
        self.path = path
        self.read_only = read_only
        if self.read_only:
            if not self.path.exists():
                raise FileNotFoundError(f"Database not found at {self.path}")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        if self.read_only:
            connection = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True, timeout=30)
        else:
            connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if not self.read_only:
            connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if self.read_only:
            raise RuntimeError("Database is opened in read-only mode")
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def apply_migrations(self, sql_dir: Path) -> None:
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)
            conn.commit()

            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }

        sql_files = sorted(sql_dir.glob("*.sql"))
        
        for sql_file in sql_files:
            version = sql_file.stem.split("_")[0]
            if version in applied:
                continue

            if version == "001":
                self._adopt_or_apply_001(sql_file, version)
            elif version == "002":
                self._adopt_or_apply_002(sql_file, version)
            elif version == "003":
                self._adopt_or_apply_003(sql_file, version)
            elif version == "004":
                # This is 004_nullable_route_ids.sql, it just updates route keys
                self._apply_migration(sql_file, version)
            elif version == "005":
                self._adopt_or_apply_005(sql_file, version)
            elif version == "006":
                self._apply_migration(sql_file, version)
            elif version == "007":
                self._adopt_or_apply_007(sql_file, version)
            else:
                self._apply_migration(sql_file, version)

    def _mark_applied(self, version: str) -> None:
        self._verify_schema(version)
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (version, now))
            conn.commit()

    def _verify_schema(self, version: str) -> None:
        with self.connect() as conn:
            if version == "001":
                tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if not {"media", "telegram_archive", "processing_events"}.issubset(tables):
                    raise RuntimeError("Verification failed: 001 tables missing.")
                indexes = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
                if not {"idx_media_state", "idx_media_updated_at"}.issubset(indexes):
                    raise RuntimeError("Verification failed: 001 indexes missing.")
            elif version == "002":
                columns_ta = {r["name"] for r in conn.execute("PRAGMA table_info(telegram_archive)").fetchall()}
                if "retry_stage" not in columns_ta:
                    raise RuntimeError("Verification failed: retry_stage missing.")
                tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if "upload_attempts" not in tables:
                    raise RuntimeError("Verification failed: upload_attempts missing.")
                
                columns_ua = {r["name"] for r in conn.execute("PRAGMA table_info(upload_attempts)").fetchall()}
                required_ua = {
                    "attempt_id", "media_id", "attempt_type", "attempt_started_at", "attempt_finished_at",
                    "request_filename", "request_size", "group_id", "topic_id", "last_http_status",
                    "outcome", "telegram_message_id", "error_code", "error_message", "next_retry_at", "uncertain_since"
                }
                if not required_ua.issubset(columns_ua):
                    raise RuntimeError(f"Verification failed: upload_attempts missing columns {required_ua - columns_ua}.")

            elif version == "003":
                columns_ta = {r["name"] for r in conn.execute("PRAGMA table_info(telegram_archive)").fetchall()}
                if "route_key" not in columns_ta:
                    raise RuntimeError("Verification failed: route_key missing.")

            elif version == "005":
                columns_media = {r["name"] for r in conn.execute("PRAGMA table_info(media)").fetchall()}
                if "cleanup_state" not in columns_media:
                    raise RuntimeError("Verification failed: cleanup_state missing in media table.")
                tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if "cleanup_attempts" not in tables:
                    raise RuntimeError("Verification failed: cleanup_attempts missing.")
            
            elif version == "006":
                tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if not {"people", "face_references", "media_faces", "face_analysis_attempts", "face_calibrations"}.issubset(tables):
                    raise RuntimeError("Verification failed: 006 tables missing.")
                columns_media = {r["name"] for r in conn.execute("PRAGMA table_info(media)").fetchall()}
                if "face_state" not in columns_media:
                    raise RuntimeError("Verification failed: face_state missing in media table.")
                    
            elif version == "007":
                columns_fc = {r["name"] for r in conn.execute("PRAGMA table_info(face_calibrations)").fetchall()}
                if "individual_strong_support_threshold" not in columns_fc:
                    raise RuntimeError("Verification failed: 007 individual_strong_support_threshold missing.")
                
    def _apply_migration(self, sql_file: Path, version: str) -> None:
        script = sql_file.read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.executescript(script)
        self._mark_applied(version)

    def _adopt_or_apply_003(self, sql_file: Path, version: str) -> None:
        with self.connect() as conn:
            columns_ta = {r["name"] for r in conn.execute("PRAGMA table_info(telegram_archive)").fetchall()}
        if "route_key" in columns_ta:
            self._mark_applied(version)
        else:
            self._apply_migration(sql_file, version)

    def repair_legacy_routing(self, config) -> None:
        if config.app.dry_run:
            return

        with self.connect() as conn:
            # Fix telegram_archive records having string topics
            records = conn.execute("SELECT media_id, topic_id FROM telegram_archive").fetchall()
            for r in records:
                mid = r["media_id"]
                topic_str = r["topic_id"]
                if topic_str and not topic_str.isdigit() and topic_str != "0":
                    numeric_topic = getattr(config.telegram.topics, topic_str, 0)
                    conn.execute(
                        "UPDATE telegram_archive SET route_key = ?, topic_id = ?, group_id = ? WHERE media_id = ?",
                        (topic_str, str(numeric_topic), config.telegram.group_id, mid)
                    )

            # Recover broken records stuck in NEEDS_REVIEW
            broken_records = conn.execute("""
                SELECT m.id FROM media m
                JOIN telegram_archive ta ON m.id = ta.media_id
                WHERE m.state = 'NEEDS_REVIEW'
                  AND ta.preview_message_id IS NULL
                  AND ta.original_message_id IS NULL
                  AND ta.telegram_file_id IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM upload_attempts ua
                      WHERE ua.media_id = m.id
                        AND (
                            ua.last_http_status IS NOT NULL
                            OR ua.telegram_message_id IS NOT NULL
                            OR ua.uncertain_since IS NOT NULL
                        )
                  )
            """).fetchall()

            for br in broken_records:
                conn.execute("UPDATE media SET state = 'READY_TO_UPLOAD' WHERE id = ?", (br["id"],))
            
            conn.commit()


    def recover_failed_original_uploads(self) -> None:
        with self.connect() as conn:
            broken_records = conn.execute("""
                SELECT m.id FROM media m
                JOIN telegram_archive ta ON m.id = ta.media_id
                WHERE m.state = 'NEEDS_REVIEW'
                  AND ta.preview_message_id IS NOT NULL
                  AND ta.original_message_id IS NULL
                  AND ta.telegram_file_id IS NULL
                  AND ta.upload_confirmed_at IS NULL
                  AND EXISTS (
                      SELECT 1 FROM upload_attempts ua
                      WHERE ua.media_id = m.id
                        AND ua.error_message LIKE '%unexpected keyword argument ''caption''%'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM upload_attempts ua
                      WHERE ua.media_id = m.id
                        AND (
                            ua.last_http_status IS NOT NULL
                            OR ua.telegram_message_id IS NOT NULL
                            OR ua.uncertain_since IS NOT NULL
                        )
                  )
            """).fetchall()

            for br in broken_records:
                # Clear error_code and error_message in media as required
                # Wait, they might not exist in some mocked tests, so we wrap in a try block just in case,
                # but production 001 schema has them.
                try:
                    conn.execute("UPDATE media SET state = 'PREVIEW_CONFIRMED', error_code = NULL, error_message = NULL WHERE id = ?", (br["id"],))
                except sqlite3.OperationalError:
                    conn.execute("UPDATE media SET state = 'PREVIEW_CONFIRMED' WHERE id = ?", (br["id"],))

            conn.commit()

    def _adopt_or_apply_001(self, sql_file: Path, version: str) -> None:
        with self.connect() as conn:
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            indexes = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
        
        has_all = {"media", "telegram_archive", "processing_events"}.issubset(tables) and {"idx_media_state", "idx_media_updated_at"}.issubset(indexes)
        
        if has_all:
            self._mark_applied(version)
        else:
            self._apply_migration(sql_file, version)

    def _adopt_or_apply_002(self, sql_file: Path, version: str) -> None:
        with self.connect() as conn:
            columns_ta = {r["name"] for r in conn.execute("PRAGMA table_info(telegram_archive)").fetchall()}
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            retry_stage_exists = "retry_stage" in columns_ta
            upload_attempts_exists = "upload_attempts" in tables

        if retry_stage_exists and upload_attempts_exists:
            # Check for missing columns in upload_attempts
            with self.connect() as conn:
                columns_ua = {r["name"] for r in conn.execute("PRAGMA table_info(upload_attempts)").fetchall()}
            
            # Map column to its sql definition for ALTER TABLE
            col_defs = {
                "attempt_id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                "media_id": "INTEGER NOT NULL",
                "attempt_type": "TEXT NOT NULL CHECK(attempt_type IN ('preview', 'original', 'original_only'))",
                "attempt_started_at": "TEXT NOT NULL",
                "attempt_finished_at": "TEXT",
                "request_filename": "TEXT",
                "request_size": "INTEGER",
                "group_id": "TEXT",
                "topic_id": "TEXT",
                "last_http_status": "INTEGER",
                "outcome": "TEXT",
                "telegram_message_id": "TEXT",
                "error_code": "TEXT",
                "error_message": "TEXT",
                "next_retry_at": "TEXT",
                "uncertain_since": "TEXT"
            }
            
            missing_cols = [c for c in col_defs if c not in columns_ua]
            if missing_cols:
                with self.connect() as conn:
                    for c in missing_cols:
                        if c == "attempt_id":
                            continue # sqlite doesn't allow adding primary key via alter table, we'll assume it exists if table exists
                        conn.execute(f"ALTER TABLE upload_attempts ADD COLUMN {c} {col_defs[c]}")
                    conn.commit()
            self._mark_applied(version)
        elif retry_stage_exists and not upload_attempts_exists:
            with self.connect() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS upload_attempts (
                        attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        media_id INTEGER NOT NULL,
                        attempt_type TEXT NOT NULL CHECK(attempt_type IN ('preview', 'original', 'original_only')),
                        attempt_started_at TEXT NOT NULL,
                        attempt_finished_at TEXT,
                        request_filename TEXT,
                        request_size INTEGER,
                        group_id TEXT,
                        topic_id TEXT,
                        last_http_status INTEGER,
                        outcome TEXT,
                        telegram_message_id TEXT,
                        error_code TEXT,
                        error_message TEXT,
                        next_retry_at TEXT,
                        uncertain_since TEXT,
                        FOREIGN KEY(media_id) REFERENCES media(id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_upload_attempts_media_id ON upload_attempts(media_id);
                """)
            self._mark_applied(version)
        else:
            self._apply_migration(sql_file, version)

    def _adopt_or_apply_004(self, sql_file: Path, version: str) -> None:
        with self.connect() as conn:
            columns_media = {r["name"] for r in conn.execute("PRAGMA table_info(media)").fetchall()}
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            
        if "cleanup_state" in columns_media and "cleanup_attempts" in tables:
            self._mark_applied(version)
        else:
            self._apply_migration(sql_file, version)


    def _adopt_or_apply_007(self, sql_file: Path, version: str) -> None:
        with self.connect() as conn:
            # Safely check if the column already exists
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "face_calibrations" not in tables:
                self._apply_migration(sql_file, version)
                return
                
            columns_fc = {r["name"] for r in conn.execute("PRAGMA table_info(face_calibrations)").fetchall()}
        
        if "individual_strong_support_threshold" in columns_fc:
            self._mark_applied(version)
        else:
            self._apply_migration(sql_file, version)

    def hash_exists(self, sha256: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM media WHERE sha256 = ? LIMIT 1",
                (sha256,),
            ).fetchone()
        return row is not None

    def reserve_media(
        self,
        sha256: str,
        short_hash: str,
        original_path: str,
        original_filename: str,
        media_type: str,
        size_bytes: int,
        modified_ns: int,
        state: str,
        timestamp: str
    ) -> int | None:
        query = """
        INSERT INTO media (
            sha256, short_hash, original_path, original_filename, 
            media_type, size_bytes, modified_ns, state, discovered_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(sha256) DO NOTHING
        """
        with self.connect() as connection:
            cursor = connection.execute(
                query,
                (
                    sha256, short_hash, original_path, original_filename,
                    media_type, size_bytes, modified_ns, state, timestamp, timestamp
                )
            )
            connection.commit()
            return cursor.lastrowid if cursor.rowcount > 0 else None

    def update_state(self, media_id: int, new_state: str, timestamp: str) -> None:
        with self.connect() as connection:
            self._update_state_internal(connection, media_id, new_state, timestamp)
            connection.commit()

    def _update_state_internal(self, connection: sqlite3.Connection, media_id: int, new_state: str, timestamp: str) -> None:
        current_state = connection.execute("SELECT state FROM media WHERE id = ?", (media_id,)).fetchone()
        if current_state:
            old_state = current_state["state"]
            if old_state != new_state and new_state not in VALID_TRANSITIONS.get(old_state, set()):
                raise RuntimeError(f"Invalid state transition: {old_state} -> {new_state}")
                
        connection.execute(
            "UPDATE media SET state = ?, updated_at = ? WHERE id = ?",
            (new_state, timestamp, media_id)
        )

    def update_metadata(
        self,
        media_id: int,
        date_taken: str | None,
        has_gps: int,
        location_label: str,
        people_json: str,
        labels_json: str,
        route_key: str,
        state: str,
        timestamp: str
    ) -> None:
        query = """
        UPDATE media
        SET date_taken = ?,
            has_gps = ?,
            location_label = ?,
            people_json = ?,
            labels_json = ?,
            updated_at = ?
        WHERE id = ?
        """
        with self.connect() as connection:
            connection.execute(
                query,
                (
                    date_taken, has_gps, location_label, people_json, 
                    labels_json, timestamp, media_id
                )
            )
            self._update_state_internal(connection, media_id, state, timestamp)
            
            connection.execute(
                "INSERT OR IGNORE INTO telegram_archive (media_id, group_id, topic_id, route_key) VALUES (?, NULL, NULL, ?)",
                (media_id, route_key)
            )
            connection.commit()

    def get_pending_uploads(self, timestamp: str, limit: int = 10) -> list[sqlite3.Row]:
        query = """
        SELECT m.id, m.original_path, m.original_filename, m.media_type, m.size_bytes, m.state, m.short_hash, m.date_taken, m.location_label,
               t.group_id, t.topic_id, t.route_key, t.preview_message_id, t.retry_stage
        FROM media m
        LEFT JOIN telegram_archive t ON m.id = t.media_id
        LEFT JOIN upload_attempts ua ON ua.media_id = m.id AND ua.attempt_finished_at IS NULL
        WHERE m.state IN ('READY_TO_UPLOAD', 'PREVIEW_CONFIRMED')
           OR (m.state = 'RETRY_WAIT' AND (
               SELECT next_retry_at FROM upload_attempts 
               WHERE media_id = m.id AND next_retry_at IS NOT NULL 
               ORDER BY attempt_started_at DESC LIMIT 1
           ) <= ?)
        GROUP BY m.id
        ORDER BY m.discovered_at ASC
        LIMIT ?
        """
        with self.connect() as conn:
            return conn.execute(query, (timestamp, limit)).fetchall()

    def start_upload_attempt(
        self,
        media_id: int,
        attempt_type: str,
        new_state: str,
        request_filename: str,
        request_size: int,
        group_id: str,
        topic_id: str,
        timestamp: str
    ) -> int:
        with self.connect() as connection:
            self._update_state_internal(connection, media_id, new_state, timestamp)
            
            connection.execute(
                "UPDATE telegram_archive SET group_id = ?, topic_id = ? WHERE media_id = ?",
                (group_id, topic_id, media_id)
            )
            
            cursor = connection.execute(
                """
                INSERT INTO upload_attempts (
                    media_id, attempt_type, attempt_started_at, request_filename, request_size, group_id, topic_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (media_id, attempt_type, timestamp, request_filename, request_size, group_id, topic_id)
            )
            connection.commit()
            return cursor.lastrowid

    def finish_upload_attempt_success(
        self,
        media_id: int,
        attempt_id: int,
        new_state: str,
        message_id: str,
        file_id: str | None,
        timestamp: str,
        is_preview: bool
    ) -> None:
        with self.connect() as connection:
            self._update_state_internal(connection, media_id, new_state, timestamp)
            
            connection.execute(
                """
                UPDATE upload_attempts
                SET attempt_finished_at = ?, outcome = 'success', telegram_message_id = ?, last_http_status = 200
                WHERE attempt_id = ?
                """,
                (timestamp, message_id, attempt_id)
            )
            
            if is_preview:
                connection.execute(
                    "UPDATE telegram_archive SET preview_message_id = ? WHERE media_id = ?",
                    (message_id, media_id)
                )
            else:
                connection.execute(
                    "UPDATE telegram_archive SET original_message_id = ?, telegram_file_id = ?, upload_confirmed_at = ? WHERE media_id = ?",
                    (message_id, file_id, timestamp, media_id)
                )
                
            connection.commit()

    def finish_upload_attempt_error(
        self,
        media_id: int,
        attempt_id: int,
        new_state: str,
        outcome: str,
        http_status: int | None,
        error_code: str,
        error_message: str,
        next_retry_at: str | None,
        retry_stage: str | None,
        timestamp: str
    ) -> None:
        with self.connect() as connection:
            self._update_state_internal(connection, media_id, new_state, timestamp)
            
            connection.execute(
                """
                UPDATE upload_attempts
                SET attempt_finished_at = ?, outcome = ?, last_http_status = ?, error_code = ?, error_message = ?, next_retry_at = ?
                WHERE attempt_id = ?
                """,
                (timestamp, outcome, http_status, error_code, error_message, next_retry_at, attempt_id)
            )
            
            if retry_stage:
                connection.execute(
                    "UPDATE telegram_archive SET retry_stage = ? WHERE media_id = ?",
                    (retry_stage, media_id)
                )
                
            connection.execute(
                "UPDATE media SET error_code = ?, error_message = ? WHERE id = ?",
                (error_code, error_message, media_id)
            )
                
            connection.commit()
            
    def mark_uncertain_uploads_needs_review(self, timestamp: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE media 
                SET state = 'NEEDS_REVIEW', updated_at = ?, error_code = 'system_restart', error_message = 'Uncertain state on restart'
                WHERE state IN ('PREVIEW_UPLOADING', 'ORIGINAL_UPLOADING')
                """,
                (timestamp,)
            )
            connection.commit()
    def get_cleanup_candidates(self, eligible_before_utc: str) -> list[dict]:
        with self.connect() as conn:
            # Candidates must be BACKED_UP
            # cleanup_state must be PENDING, ELIGIBLE, or FAILED (retry)
            # must have upload_confirmed_at < eligible_before_utc
            # telegram_file_id and original_message_id must exist
            # must not have unfinished or uncertain upload attempts
            query = """
                SELECT m.id, m.sha256, m.short_hash, m.original_path, m.original_filename
                FROM media m
                JOIN telegram_archive ta ON m.id = ta.media_id
                WHERE m.state = 'BACKED_UP'
                  AND m.cleanup_state IN ('PENDING', 'ELIGIBLE', 'FAILED')
                  AND ta.upload_confirmed_at IS NOT NULL
                  AND ta.upload_confirmed_at < ?
                  AND ta.telegram_file_id IS NOT NULL
                  AND ta.original_message_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM upload_attempts ua
                      WHERE ua.media_id = m.id
                        AND (ua.attempt_finished_at IS NULL
                             OR ua.outcome = 'UNCERTAIN'
                             OR ua.uncertain_since IS NOT NULL)
                  )
            """
            return [dict(row) for row in conn.execute(query, (eligible_before_utc,)).fetchall()]

    def start_cleanup_attempt(self, media_id: int, mode: str, source_path: str, destination_path: str, started_at: str) -> int:
        with self.connect() as conn:
            conn.execute("UPDATE media SET cleanup_state = 'IN_PROGRESS' WHERE id = ?", (media_id,))
            cursor = conn.execute(
                """
                INSERT INTO cleanup_attempts (media_id, mode, source_path, destination_path, attempt_started_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (media_id, mode, source_path, destination_path, started_at)
            )
            conn.commit()
            return cursor.lastrowid

    def finish_cleanup_attempt(self, media_id: int, attempt_id: int, outcome: str, state: str, error_code: str = None, error_message: str = None, finished_at: str = None) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE media SET cleanup_state = ? WHERE id = ?", (state, media_id))
            if attempt_id:
                conn.execute(
                    """
                    UPDATE cleanup_attempts
                    SET attempt_finished_at = ?, outcome = ?, error_code = ?, error_message = ?
                    WHERE attempt_id = ?
                    """,
                    (finished_at, outcome, error_code, error_message, attempt_id)
                )
            conn.commit()

    def get_blocked_cleanup_records(self) -> list[dict]:
        with self.connect() as conn:
            query = """
                SELECT id, original_filename, cleanup_state
                FROM media
                WHERE cleanup_state IN ('SOURCE_CHANGED', 'SOURCE_MISSING', 'NEEDS_REVIEW')
            """
            return [dict(row) for row in conn.execute(query).fetchall()]

    def get_in_progress_cleanups(self) -> list[dict]:
        with self.connect() as conn:
            query = """
                SELECT m.id, m.sha256, m.original_path, ca.attempt_id, ca.destination_path, ca.mode
                FROM media m
                JOIN cleanup_attempts ca ON m.id = ca.media_id
                WHERE m.cleanup_state = 'IN_PROGRESS'
                  AND ca.attempt_finished_at IS NULL
            """
            return [dict(row) for row in conn.execute(query).fetchall()]


    def _adopt_or_apply_005(self, sql_file: Path, version: str) -> None:
        with self.connect() as conn:
            columns_media = {r["name"] for r in conn.execute("PRAGMA table_info(media)").fetchall()}
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            
        if "cleanup_state" in columns_media and "cleanup_attempts" in tables:
            self._mark_applied(version)
        else:
            self._apply_migration(sql_file, version)

    # --- Face Database Methods ---
    
    def find_person_by_slug(self, person_slug: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM people WHERE person_slug = ?", (person_slug,)).fetchone()
            return dict(row) if row else None
            
    def get_or_create_person(self, person_slug: str, display_name: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            row = conn.execute("SELECT person_id, display_name, active FROM people WHERE person_slug = ?", (person_slug,)).fetchone()
            if row:
                person_id = row["person_id"]
                if row["display_name"] != display_name or not row["active"]:
                    conn.execute("UPDATE people SET display_name = ?, active = 1, updated_at = ? WHERE person_id = ?", (display_name, now, person_id))
                return person_id
                
            cursor = conn.execute(
                "INSERT INTO people (person_slug, display_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (person_slug, display_name, now, now)
            )
            return cursor.lastrowid
            
    def reference_exists(self, source_sha256: str) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM face_references WHERE source_sha256 = ?", (source_sha256,)).fetchone() is not None

    def add_reference(self, person_id: int, source_sha256: str, source_path: str, detector_confidence: float, face_width: int, face_height: int, quality_json: str, embedding_blob: bytes, embedding_dimension: int, model_identity: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO face_references "
                "(person_id, source_sha256, source_path, detector_confidence, face_width, face_height, quality_json, embedding_blob, embedding_dimension, model_identity, enrolled_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (person_id, source_sha256, source_path, detector_confidence, face_width, face_height, quality_json, embedding_blob, embedding_dimension, model_identity, now)
            )
            return cursor.lastrowid

    def add_rejected_reference(self, person_id: int, source_sha256: str, source_path: str, rejection_code: str, rejection_message: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO face_references "
                "(person_id, source_sha256, source_path, active, enrolled_at, rejection_code, rejection_message) "
                "VALUES (?, ?, ?, 0, ?, ?, ?)",
                (person_id, source_sha256, source_path, now, rejection_code, rejection_message)
            )
            
    def get_active_people(self) -> list[dict]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM people WHERE active = 1 ORDER BY person_slug").fetchall()]

    def deactivate_person(self, person_slug: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            cursor = conn.execute("UPDATE people SET active = 0, updated_at = ? WHERE person_slug = ?", (now, person_slug))
            if cursor.rowcount > 0:
                person_id = conn.execute("SELECT person_id FROM people WHERE person_slug = ?", (person_slug,)).fetchone()["person_id"]
                conn.execute("UPDATE face_references SET active = 0 WHERE person_id = ?", (person_id,))
                return True
            return False

    def get_active_references(self, model_identity: str) -> list[dict]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT fr.*, p.person_slug, p.display_name "
                "FROM face_references fr "
                "JOIN people p ON fr.person_id = p.person_id "
                "WHERE fr.active = 1 AND p.active = 1 AND fr.model_identity = ? AND fr.embedding_blob IS NOT NULL AND fr.rejection_code IS NULL",
                (model_identity,)
            ).fetchall()]

    def get_active_calibration(self, model_identity: str, reference_set_hash: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM face_calibrations "
                "WHERE active = 1 AND model_identity = ? AND reference_set_hash = ? "
                "ORDER BY generated_at DESC LIMIT 1",
                (model_identity, reference_set_hash)
            ).fetchone()
            return dict(row) if row else None

    def activate_calibration(self, model_identity: str, reference_set_hash: str, accept_threshold: float, review_threshold: float, minimum_margin: float, individual_strong_support_threshold: float, positive_pair_count: int, negative_pair_count: int, report_json: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE face_calibrations "
                "SET active = 0 "
                "WHERE active = 1 AND model_identity = ?",
                (model_identity,)
            )
            conn.execute(
                "INSERT INTO face_calibrations "
                "(model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, generated_at, report_json, active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, now, report_json)
            )

    def get_pending_face_analysis(self, limit: int = 10) -> list[dict]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT id, sha256, original_path, state FROM media WHERE face_state = 'PENDING' AND state NOT IN ('BACKED_UP', 'CLEANED') LIMIT ?",
                (limit,)
            ).fetchall()]

    def start_face_analysis_attempt(self, media_id: int, analysis_key: str, analysis_version: int, model_identity: str, reference_set_hash: str, calibration_id: int | None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            row = conn.execute("SELECT attempt_id, outcome FROM face_analysis_attempts WHERE media_id = ? AND analysis_key = ? AND analysis_version = ?", (media_id, analysis_key, analysis_version)).fetchone()
            if row:
                return row["attempt_id"]
                
            cursor = conn.execute(
                "INSERT INTO face_analysis_attempts "
                "(media_id, analysis_key, analysis_version, model_identity, reference_set_hash, calibration_id, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, calibration_id, now)
            )
            conn.execute("UPDATE media SET face_state = 'ANALYZING' WHERE id = ?", (media_id,))
            return cursor.lastrowid
            
    def record_face_analysis_success(self, media_id: int, attempt_id: int, faces: list[dict]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            for face in faces:
                conn.execute(
                    "INSERT INTO media_faces "
                    "(media_id, attempt_id, face_index, bounding_box_json, landmarks_json, detector_confidence, quality_json, embedding_blob, embedding_dimension, model_identity, best_person_id, best_score, second_best_person_id, second_best_score, score_margin, supporting_reference_count, decision, analyzed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (media_id, attempt_id, face.get("face_index"), face.get("bounding_box_json"), face.get("landmarks_json"), face.get("detector_confidence"), face.get("quality_json"), face.get("embedding_blob"), face.get("embedding_dimension"), face.get("model_identity"), face.get("best_person_id"), face.get("best_score"), face.get("second_best_person_id"), face.get("second_best_score"), face.get("score_margin"), face.get("supporting_reference_count"), face.get("decision"), now)
                )
                
            detected_face_count = len(faces)
            accepted_match_count = sum(1 for f in faces if f.get("best_person_id") is not None and "UNKNOWN" not in f.get("decision", ""))
            unknown_face_count = detected_face_count - accepted_match_count
            
            conn.execute(
                "UPDATE face_analysis_attempts "
                "SET finished_at = ?, outcome = 'SUCCESS', detected_face_count = ?, accepted_match_count = ?, unknown_face_count = ? "
                "WHERE attempt_id = ?",
                (now, detected_face_count, accepted_match_count, unknown_face_count, attempt_id)
            )
            
            face_state = 'ANALYZED'
            if detected_face_count == 0:
                face_state = 'NO_FACE'
            elif any("NEEDS_REVIEW" in f.get("decision", "") or "AMBIGUOUS" in f.get("decision", "") for f in faces):
                face_state = 'NEEDS_REVIEW'
                
            conn.execute("UPDATE media SET face_state = ? WHERE id = ?", (face_state, media_id))

    def record_face_analysis_failure(self, media_id: int, attempt_id: int, error_code: str, error_message: str, new_face_state: str = 'FAILED') -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE face_analysis_attempts "
                "SET finished_at = ?, outcome = 'FAILURE', error_code = ?, error_message = ? "
                "WHERE attempt_id = ?",
                (now, error_code, error_message, attempt_id)
            )
            conn.execute("UPDATE media SET face_state = ? WHERE id = ?", (new_face_state, media_id))
    def get_media_people_names(self, media_id: int) -> list[str]:
        with self.connect() as conn:
            # We want names where decision is ACCEPTED or we just take best_person_id?
            # "accepted_match_count" implies we only want ACCEPTED.
            rows = conn.execute(
                "SELECT p.display_name FROM media_faces mf JOIN people p ON mf.best_person_id = p.person_id WHERE mf.media_id = ? AND mf.decision = 'ACCEPTED' ORDER BY p.display_name",
                (media_id,)
            ).fetchall()
            return [r["display_name"] for r in rows]
