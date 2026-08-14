import pytest
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from src.routing import choose_topic, RouteInput

# We can simulate the database state changes across orchestration directly.

def setup_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # minimal schema for routing tests
    conn.executescript("""
        CREATE TABLE media (
            id INTEGER PRIMARY KEY,
            media_type TEXT,
            has_gps BOOLEAN,
            labels_json TEXT DEFAULT '[]'
        );
        CREATE TABLE telegram_archive (
            media_id INTEGER,
            route_key TEXT
        );
    """)
    return conn

def test_orchestration_order_screenshot_no_face_no_gps(tmp_path: Path):
    # 1. Scanner adds media: no gps
    conn = setup_db(tmp_path / "test.db")
    conn.execute("INSERT INTO media (id, media_type, has_gps, labels_json) VALUES (1, 'image', 0, '[]')")
    # Scanner calculates initial route: misc (because no gps, no labels, no people)
    initial_route = choose_topic(RouteInput("image", (), (), False))
    assert initial_route == "misc"
    conn.execute("INSERT INTO telegram_archive (media_id, route_key) VALUES (1, ?)", (initial_route,))
    
    # 2. Face Worker runs. Finds NO face (or unknown). 
    # It passes empty labels because it doesn't know about scene yet.
    # It evaluates RouteInput("image", ("Unknown Person",), (), False) -> misc
    # Since 'misc' not in ("people", "family_groups"), it returns WITHOUT updating DB.
    face_eval_route = choose_topic(RouteInput("image", ("Unknown Person",), (), False))
    assert face_eval_route == "misc"
    if face_eval_route in ("people", "family_groups"):
        conn.execute("UPDATE telegram_archive SET route_key = ? WHERE media_id = 1", (face_eval_route,))
    
    current_route = conn.execute("SELECT route_key FROM telegram_archive WHERE media_id = 1").fetchone()[0]
    assert current_route == "misc", "Unknown face correctly didn't finalize route to people"
    
    # 3. Scene Worker runs. Persists screenshot label.
    # Recomputes route with complete context.
    conn.execute("UPDATE media SET labels_json = ? WHERE id = 1", (json.dumps(["screenshot"]),))
    
    scene_eval_route = choose_topic(RouteInput("image", ("Unknown Person",), ("screenshot",), False))
    assert scene_eval_route == "screenshots_documents"
    
    conn.execute("UPDATE telegram_archive SET route_key = ? WHERE media_id = 1", (scene_eval_route,))
    final_route = conn.execute("SELECT route_key FROM telegram_archive WHERE media_id = 1").fetchone()[0]
    assert final_route == "screenshots_documents", "Scene correctly finalized route to screenshots_documents"

def test_orchestration_order_screenshot_known_face(tmp_path: Path):
    # 1. Scanner adds media: no gps -> misc
    conn = setup_db(tmp_path / "test.db")
    conn.execute("INSERT INTO media (id, media_type, has_gps, labels_json) VALUES (1, 'image', 0, '[]')")
    conn.execute("INSERT INTO telegram_archive (media_id, route_key) VALUES (1, 'misc')")
    
    # 2. Face Worker runs. Finds 1 KNOWN face.
    face_eval_route = choose_topic(RouteInput("image", ("Person One",), (), False))
    assert face_eval_route == "people"
    if face_eval_route in ("people", "family_groups"):
        conn.execute("UPDATE telegram_archive SET route_key = ? WHERE media_id = 1", (face_eval_route,))
        
    current_route = conn.execute("SELECT route_key FROM telegram_archive WHERE media_id = 1").fetchone()[0]
    assert current_route == "people"
    
    # 3. Scene Worker runs. Persists screenshot label.
    conn.execute("UPDATE media SET labels_json = ? WHERE id = 1", (json.dumps(["screenshot"]),))
    
    # It evaluates RouteInput with the known person and screenshot
    scene_eval_route = choose_topic(RouteInput("image", ("Person One",), ("screenshot",), False))
    assert scene_eval_route == "people", "Known person precedence overrides screenshot"
    
    conn.execute("UPDATE telegram_archive SET route_key = ? WHERE media_id = 1", (scene_eval_route,))
    final_route = conn.execute("SELECT route_key FROM telegram_archive WHERE media_id = 1").fetchone()[0]
    assert final_route == "people", "Route remains people after scene stage"
