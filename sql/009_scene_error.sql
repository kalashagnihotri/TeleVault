-- Add scene error columns to media table
ALTER TABLE media ADD COLUMN scene_error_code TEXT;
ALTER TABLE media ADD COLUMN scene_error_message TEXT;
