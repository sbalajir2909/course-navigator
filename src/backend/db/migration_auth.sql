-- Add auth columns to students table
ALTER TABLE students ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS auth_token TEXT;
CREATE INDEX IF NOT EXISTS idx_students_auth_token ON students(auth_token);
