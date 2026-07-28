import threading
import sqlite3
import pytest
from pathlib import Path
from src.database import ArchiveDatabase

def test_duplicate_race(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    
    db.apply_migrations(Path("sql"))
    hash_val = "1234567890abcdef"
    results = []
    
    def worker():
        try:
            res = db.reserve_media(
                sha256=hash_val,
                short_hash="12345678",
                original_path="/dummy/path.jpg",
                original_filename="path.jpg",
                media_type="image",
                size_bytes=100,
                modified_ns=1000,
                state="RESERVED",
                timestamp="2026-01-01T00:00:00"
            )
            results.append(res)
        except Exception as e:
            results.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Only one thread should have received a non-None media_id (the successful insert)
    # The others should have received None (due to DO NOTHING on conflict)
    # Filter out exceptions if any
    valid_results = [r for r in results if not isinstance(r, Exception)]
    successful_inserts = [r for r in valid_results if r is not None]
    
    assert len(successful_inserts) == 1, "Only one worker should successfully reserve the hash"
    assert len(valid_results) == 10, "All workers should complete without DB lock errors"
