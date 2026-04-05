-- Enable pgvector extension for embeddings
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────
-- PROFESSORS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS professors (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_professors_email ON professors(email);

-- ─────────────────────────────────────────────
-- COURSES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS courses (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id    UUID NOT NULL REFERENCES professors(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'processing',  -- processing | ready | failed
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_courses_professor_id ON courses(professor_id);
CREATE INDEX IF NOT EXISTS idx_courses_status ON courses(status);

-- ─────────────────────────────────────────────
-- SOURCE DOCUMENTS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS source_documents (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id   UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,
    raw_text    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_documents_course_id ON source_documents(course_id);

-- ─────────────────────────────────────────────
-- CHUNKS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    chunk_index     INT NOT NULL,
    embedding       vector(1536),
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ─────────────────────────────────────────────
-- MODULES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS modules (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id               UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title                   TEXT NOT NULL,
    description             TEXT,
    learning_objectives     TEXT[] DEFAULT ARRAY[]::TEXT[],
    source_chunk_ids        UUID[] DEFAULT ARRAY[]::UUID[],
    order_index             INT NOT NULL DEFAULT 0,
    source_type             TEXT NOT NULL DEFAULT 'material',  -- material | parametric
    faithfulness_verdict    TEXT,  -- FAITHFUL | PARTIAL | UNFAITHFUL
    faithfulness_details    JSONB DEFAULT '{}'::jsonb,
    estimated_minutes       INT DEFAULT 30,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_modules_course_id ON modules(course_id);
CREATE INDEX IF NOT EXISTS idx_modules_order ON modules(course_id, order_index);

-- ─────────────────────────────────────────────
-- PREREQUISITES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prerequisites (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    module_id               UUID NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    prerequisite_module_id  UUID NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    UNIQUE(module_id, prerequisite_module_id)
);

CREATE INDEX IF NOT EXISTS idx_prerequisites_module_id ON prerequisites(module_id);
CREATE INDEX IF NOT EXISTS idx_prerequisites_prereq_id ON prerequisites(prerequisite_module_id);

-- ─────────────────────────────────────────────
-- ASSESSMENTS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS assessments (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    module_id       UUID NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    question        TEXT NOT NULL,
    question_type   TEXT NOT NULL,   -- multiple_choice | short_answer
    options         JSONB,           -- for multiple_choice: ["A", "B", "C", "D"]
    correct_answer  TEXT NOT NULL,
    difficulty_tier TEXT NOT NULL,   -- recall | application | synthesis
    source_chunk_ids UUID[] DEFAULT ARRAY[]::UUID[],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assessments_module_id ON assessments(module_id);

-- ─────────────────────────────────────────────
-- STUDENTS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS students (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_students_email ON students(email);

-- ─────────────────────────────────────────────
-- ENROLLMENTS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS enrollments (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id  UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id   UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(student_id, course_id)
);

CREATE INDEX IF NOT EXISTS idx_enrollments_student_id ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_course_id ON enrollments(course_id);

-- ─────────────────────────────────────────────
-- SESSIONS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id      UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    module_id       UUID NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    mastery_score   FLOAT DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_sessions_student_id ON sessions(student_id);
CREATE INDEX IF NOT EXISTS idx_sessions_module_id ON sessions(module_id);

-- ─────────────────────────────────────────────
-- KC ATTEMPTS (Knowledge Check Attempts)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kc_attempts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    module_id           UUID NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    student_explanation TEXT NOT NULL,
    validator_scores    JSONB DEFAULT '{}'::jsonb,
    mastery_probability FLOAT DEFAULT 0.0,
    attempt_number      INT NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kc_attempts_session_id ON kc_attempts(session_id);
CREATE INDEX IF NOT EXISTS idx_kc_attempts_module_id ON kc_attempts(module_id);
