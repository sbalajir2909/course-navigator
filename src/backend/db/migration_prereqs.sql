CREATE TABLE IF NOT EXISTS student_prerequisite_recommendations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id UUID REFERENCES students(id) ON DELETE CASCADE,
  module_id UUID REFERENCES modules(id),
  topic TEXT NOT NULL,
  reason TEXT NOT NULL,
  brief_explanation TEXT NOT NULL,
  is_in_course BOOLEAN DEFAULT false,
  linked_module_id UUID REFERENCES modules(id),
  status TEXT DEFAULT 'recommended',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE student_progress ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS notes TEXT;

CREATE TABLE IF NOT EXISTS student_progress (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id UUID REFERENCES students(id) ON DELETE CASCADE,
  module_id UUID REFERENCES modules(id) ON DELETE CASCADE,
  course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
  status TEXT DEFAULT 'not_started',
  mastery_score FLOAT DEFAULT 0.0,
  attempts INTEGER DEFAULT 0,
  notes TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(student_id, module_id)
);

CREATE TABLE IF NOT EXISTS assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  instructions TEXT NOT NULL,
  rubric JSONB NOT NULL DEFAULT '[]',
  difficulty TEXT NOT NULL DEFAULT 'standard',
  target_students TEXT DEFAULT 'all',
  target_module_ids TEXT[] DEFAULT '{}',
  estimated_minutes INTEGER DEFAULT 30,
  status TEXT DEFAULT 'pending_approval',
  due_date TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS assignment_submissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id UUID REFERENCES assignments(id) ON DELETE CASCADE,
  student_id UUID REFERENCES students(id) ON DELETE CASCADE,
  submission_text TEXT NOT NULL,
  auto_grade_result JSONB,
  auto_grade_total FLOAT,
  professor_override_grade FLOAT,
  professor_feedback TEXT,
  grade_released BOOLEAN DEFAULT false,
  submitted_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(assignment_id, student_id)
);
