-- Add concepts column to modules (JSONB array of atomic concepts)
ALTER TABLE modules ADD COLUMN IF NOT EXISTS concepts JSONB DEFAULT '[]'::jsonb;

-- Index for faster concept lookups
CREATE INDEX IF NOT EXISTS idx_modules_course_id_concepts ON modules(course_id) WHERE concepts IS NOT NULL;
