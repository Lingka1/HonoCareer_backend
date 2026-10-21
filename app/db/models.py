"""SQLite schema. Immutable snapshots preserve historical context."""
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, account TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 nickname TEXT NOT NULL, avatar_url TEXT, memory_enabled INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_sessions (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 refresh_hash TEXT NOT NULL UNIQUE, expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS profiles (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), type TEXT NOT NULL,
 display_name TEXT NOT NULL, base_info TEXT NOT NULL, detail TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resumes (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), file_name TEXT NOT NULL,
 mime_type TEXT NOT NULL, file_data BLOB NOT NULL, status TEXT NOT NULL,
 parsed_content TEXT NOT NULL DEFAULT '{}', job_id TEXT, error TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), client_session_id TEXT NOT NULL,
 request_hash TEXT NOT NULL, title TEXT NOT NULL, mode TEXT NOT NULL, scene TEXT NOT NULL,
 scene_config TEXT NOT NULL, profile_snapshot TEXT NOT NULL, resume_snapshot TEXT,
 modality TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL, stage_turns INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, ended_at TEXT,
 UNIQUE(user_id, client_session_id)
);
CREATE TABLE IF NOT EXISTS messages (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 seq INTEGER NOT NULL, role TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
 input_mode TEXT NOT NULL, stage TEXT NOT NULL, audio_id TEXT, created_at TEXT NOT NULL,
 UNIQUE(session_id, seq)
);
CREATE TABLE IF NOT EXISTS responses (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 client_message_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 user_message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
 status TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(session_id, client_message_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_running_response ON responses(session_id)
 WHERE status IN ('queued','processing');
CREATE TABLE IF NOT EXISTS events (
 id TEXT PRIMARY KEY, response_id TEXT NOT NULL REFERENCES responses(id) ON DELETE CASCADE,
 seq INTEGER NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(response_id,seq)
);
CREATE TABLE IF NOT EXISTS reports (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL UNIQUE REFERENCES sessions(id) ON DELETE CASCADE,
 status TEXT NOT NULL, content TEXT, error TEXT, created_at TEXT NOT NULL, generated_at TEXT
);
CREATE TABLE IF NOT EXISTS weak_points (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id), dimension_key TEXT NOT NULL,
 message_ids TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 content TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency (
 user_id TEXT NOT NULL, scope TEXT NOT NULL, key TEXT NOT NULL, request_hash TEXT NOT NULL,
 resource_id TEXT NOT NULL, PRIMARY KEY(user_id,scope,key)
);
CREATE INDEX IF NOT EXISTS session_history ON sessions(user_id,updated_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS profile_history ON profiles(user_id,type,updated_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS message_history ON messages(session_id,seq);
PRAGMA user_version=1;
"""
