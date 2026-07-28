CREATE TABLE telegram_archive_new (
    media_id INTEGER PRIMARY KEY,
    group_id TEXT,
    topic_id TEXT,
    preview_message_id TEXT,
    original_message_id TEXT,
    telegram_file_id TEXT,
    upload_confirmed_at TEXT,
    retry_stage TEXT,
    route_key TEXT,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

INSERT INTO telegram_archive_new (
    media_id, group_id, topic_id, preview_message_id, 
    original_message_id, telegram_file_id, upload_confirmed_at, 
    retry_stage, route_key
)
SELECT 
    media_id, 
    CASE WHEN group_id = '' THEN NULL ELSE group_id END,
    CASE WHEN topic_id = '' THEN NULL ELSE topic_id END,
    preview_message_id, 
    original_message_id, 
    telegram_file_id, 
    upload_confirmed_at, 
    retry_stage, 
    route_key 
FROM telegram_archive;

DROP TABLE telegram_archive;
ALTER TABLE telegram_archive_new RENAME TO telegram_archive;
