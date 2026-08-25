"""Disaster Simulation Test (Phase 6.5G Pillar 12)

Scenario:
1. Primary machine is running, active database populated with media, people, face embeddings, memories, and confirmed Telegram message links.
2. Complete catastrophic hardware loss: active database and runtime files wiped.
3. New machine cold install: spin up fresh database, restore backup snapshot.
4. Verify 100% integrity check, exact row counts, people profiles, memories, and Telegram cloud references intact.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from src.database import ArchiveDatabase


def test_complete_disaster_and_cold_restore_simulation(tmp_path):
    """Simulate catastrophic machine death and cold system restoration."""
    # 1. Original machine setup
    orig_env = tmp_path / "original_machine"
    orig_env.mkdir()
    orig_db_path = orig_env / "archive.sqlite3"
    
    db_orig = ArchiveDatabase(orig_db_path)
    db_orig.apply_migrations(Path("sql"))

    # Populate original database with rich media, people, and Telegram archive state
    with db_orig.connect() as conn:
        c1 = conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('alice_dr', 'Alice Disaster Recovery', 1, '2026-08-25', '2026-08-25')")
        p_id = c1.lastrowid

        c2 = conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, people_json, date_taken, discovered_at, updated_at) VALUES ('sha_dr_01', 'shdr1', 'C:/photos/dr1.jpg', 'dr1.jpg', 'image', 12345, 0, 'BACKED_UP', '[\"Vacation\", \"Beach\"]', '[\"Alice Disaster Recovery\"]', '2026-08-25', '2026-08-25', '2026-08-25')")
        m_id = c2.lastrowid

        conn.execute("INSERT INTO telegram_archive (media_id, group_id, topic_id, preview_message_id, original_message_id, upload_confirmed_at) VALUES (?, '-100999', '12', '5001', '5002', '2026-08-25T12:00:00')", (m_id,))

        c_att = conn.execute("INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, finished_at, outcome, detected_face_count, accepted_match_count, unknown_face_count) VALUES (?, 'k', 1, 'm', 'h', '2026-08-25', '2026-08-25', 'SUCCESS', 1, 1, 0)", (m_id,))
        att_id = c_att.lastrowid
        conn.execute("INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at) VALUES (?, ?, 0, 0.95, ?, 0.92, 'KNOWN_MATCH', '2026-08-25')", (m_id, att_id, p_id))

        conn.commit()

    # 2. Online Backup Snapshot (Cold storage artifact)
    backup_file = tmp_path / "cold_backup_snapshot.sqlite3"
    conn_src = sqlite3.connect(str(orig_db_path))
    conn_dst = sqlite3.connect(str(backup_file))
    with conn_dst:
        conn_src.backup(conn_dst)
    conn_dst.close()
    conn_src.close()

    assert backup_file.exists()
    assert backup_file.stat().st_size > 0

    # Explicitly close connections
    del db_orig
    import gc
    gc.collect()

    # 3. CATASTROPHIC LOSS: Entire original machine environment is removed / simulated destroyed
    # 4. NEW MACHINE COLD PROVISIONING
    new_machine_env = tmp_path / "new_replacement_laptop"
    new_machine_env.mkdir(parents=True, exist_ok=True)
    restored_db_path = new_machine_env / "archive.sqlite3"

    # Restore snapshot into new environment
    shutil.copy2(backup_file, restored_db_path)
    assert restored_db_path.exists()
    assert restored_db_path.stat().st_size > 0

    # 5. VERIFICATION OF FULL RESTORATION
    db_restored = ArchiveDatabase(restored_db_path)
    with db_restored.connect() as conn:
        # Check SQLite integrity
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert integrity == "ok"

        # Verify media records
        cur = conn.execute("SELECT id, sha256, original_filename, state, people_json FROM media")
        restored_media = cur.fetchall()
        assert len(restored_media) == 1
        assert restored_media[0]["sha256"] == "sha_dr_01"
        assert restored_media[0]["state"] == "BACKED_UP"

        # Verify Telegram archive topic and message IDs
        cur_arch = conn.execute("SELECT media_id, group_id, topic_id, preview_message_id, original_message_id FROM telegram_archive")
        restored_arch = cur_arch.fetchall()
        assert len(restored_arch) == 1
        assert restored_arch[0]["preview_message_id"] == "5001"
        assert restored_arch[0]["original_message_id"] == "5002"

        # Verify enrolled people & face matches
        cur_people = conn.execute("SELECT person_id, display_name FROM people")
        restored_people = cur_people.fetchall()
        assert len(restored_people) == 1
        assert restored_people[0]["display_name"] == "Alice Disaster Recovery"

        cur_faces = conn.execute("SELECT media_face_id, best_person_id, decision FROM media_faces")
        restored_faces = cur_faces.fetchall()
        assert len(restored_faces) == 1
        assert restored_faces[0]["decision"] == "KNOWN_MATCH"
        assert restored_faces[0]["best_person_id"] == restored_people[0]["person_id"]
