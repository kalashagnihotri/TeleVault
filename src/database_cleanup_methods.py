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
