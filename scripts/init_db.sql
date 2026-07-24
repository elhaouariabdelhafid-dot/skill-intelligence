-- Schéma initial — exécuté automatiquement au premier démarrage du conteneur
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    role        TEXT DEFAULT 'collaborator',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS skills (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    domain      TEXT,                      -- ex: Design Secure Architectures
    parent_id   INT REFERENCES skills(id)
);

CREATE TABLE IF NOT EXISTS questions (
    id              SERIAL PRIMARY KEY,
    skill_id        INT REFERENCES skills(id),
    level           TEXT CHECK (level IN ('beginner','intermediate','advanced')),
    text            TEXT NOT NULL,
    expected_answer TEXT,
    rubric          JSONB,
    source_chunks   JSONB,                 -- ids des chunks d'ancrage
    status          TEXT DEFAULT 'candidate',  -- candidate | accepted | rejected
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS submissions (
    id          SERIAL PRIMARY KEY,
    user_id     INT REFERENCES users(id),
    question_id INT REFERENCES questions(id),
    answer_text TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evaluations (
    id             SERIAL PRIMARY KEY,
    submission_id  INT REFERENCES submissions(id),
    agent_scores   JSONB,      -- {grader: {...}, reasoner: {...}, critic: {...}}
    final_score    NUMERIC(4,2),
    feedback       JSONB,
    citations      JSONB,
    created_at     TIMESTAMPTZ DEFAULT now()
);
