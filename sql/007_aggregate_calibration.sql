ALTER TABLE face_calibrations ADD COLUMN individual_strong_support_threshold REAL NOT NULL DEFAULT 0.0;

UPDATE face_calibrations SET individual_strong_support_threshold = accept_threshold;
