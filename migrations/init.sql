CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    user_name TEXT,
    files_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS files (
    file_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id_int INTEGER NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    complexity INTEGER NOT NULL,
    size INTEGER NOT NULL,
    labels TEXT[]
);

CREATE TABLE IF NOT EXISTS requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    file_id UUID NOT NULL REFERENCES files(file_id)
);

CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id);
CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests(user_id);
CREATE INDEX IF NOT EXISTS idx_requests_file_id ON requests(file_id);
