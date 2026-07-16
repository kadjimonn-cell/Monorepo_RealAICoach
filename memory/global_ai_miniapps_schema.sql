-- RealAICoach Global AI Platform Expansion Schema (PostgreSQL)

CREATE TABLE users (
    user_id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    roles TEXT[] DEFAULT ARRAY['user'],
    subscription_plan VARCHAR(50),
    subscription_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE employers (
    employer_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    company_name VARCHAR(255) NOT NULL,
    company_logo TEXT,
    location VARCHAR(255),
    website TEXT,
    description TEXT,
    subscription_plan VARCHAR(50),
    subscription_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    employer_id VARCHAR(64) REFERENCES employers(employer_id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    company_name VARCHAR(255),
    company_logo TEXT,
    location VARCHAR(255),
    remote BOOLEAN DEFAULT FALSE,
    salary_min INTEGER,
    salary_max INTEGER,
    description TEXT,
    skills_required TEXT[],
    category VARCHAR(100),
    job_type VARCHAR(100),
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE job_applications (
    application_id VARCHAR(64) PRIMARY KEY,
    job_id VARCHAR(64) REFERENCES jobs(job_id) ON DELETE CASCADE,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    resume_text TEXT,
    resume_title VARCHAR(255),
    cover_letter TEXT,
    skills TEXT[],
    status VARCHAR(50) DEFAULT 'submitted',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE resumes (
    resume_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    title VARCHAR(255),
    summary TEXT,
    experience TEXT[],
    education TEXT[],
    skills TEXT[],
    certifications TEXT[],
    projects TEXT[],
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE saved_jobs (
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    job_id VARCHAR(64) REFERENCES jobs(job_id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, job_id)
);

CREATE TABLE mobile_money_payments (
    payment_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    plan_id VARCHAR(50),
    billing_period VARCHAR(50),
    provider VARCHAR(50),
    phone_number VARCHAR(50),
    amount NUMERIC(12,2),
    currency VARCHAR(10),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE mobile_money_transactions (
    transaction_id VARCHAR(64) PRIMARY KEY,
    payment_id VARCHAR(64) REFERENCES mobile_money_payments(payment_id) ON DELETE CASCADE,
    provider VARCHAR(50),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE subscriptions (
    subscription_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    plan_id VARCHAR(50),
    status VARCHAR(50),
    provider VARCHAR(50),
    started_at TIMESTAMP DEFAULT NOW(),
    billing_period VARCHAR(50)
);

CREATE TABLE accounting_income (
    income_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    title VARCHAR(255),
    amount NUMERIC(12,2),
    currency VARCHAR(10),
    category VARCHAR(100),
    date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE accounting_expenses (
    expense_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    title VARCHAR(255),
    amount NUMERIC(12,2),
    currency VARCHAR(10),
    category VARCHAR(100),
    date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE accounting_reports (
    report_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE drama_videos (
    drama_id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255),
    description TEXT,
    genre VARCHAR(100),
    file_name TEXT,
    stream_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE drama_history (
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    drama_id VARCHAR(64) REFERENCES drama_videos(drama_id) ON DELETE CASCADE,
    watched_at TIMESTAMP DEFAULT NOW(),
    progress_seconds INTEGER DEFAULT 0
);

CREATE TABLE drama_favorites (
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    drama_id VARCHAR(64) REFERENCES drama_videos(drama_id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, drama_id)
);

CREATE TABLE songs (
    song_id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255),
    artist VARCHAR(255),
    genre VARCHAR(100),
    file_name TEXT,
    stream_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE playlists (
    playlist_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    name VARCHAR(255),
    song_ids TEXT[],
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE music_history (
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    song_id VARCHAR(64) REFERENCES songs(song_id) ON DELETE CASCADE,
    played_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE local_music (
    track_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    title VARCHAR(255),
    artist VARCHAR(255),
    file_name TEXT,
    stream_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE local_music_libraries (
    library_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    name VARCHAR(255),
    track_ids TEXT[],
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE invoice_clients (
    client_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    address TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE invoices (
    invoice_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(user_id) ON DELETE CASCADE,
    client_id VARCHAR(64) REFERENCES invoice_clients(client_id) ON DELETE SET NULL,
    currency VARCHAR(10),
    total NUMERIC(12,2),
    status VARCHAR(50),
    due_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE invoice_items (
    item_id VARCHAR(64) PRIMARY KEY,
    invoice_id VARCHAR(64) REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    description TEXT,
    quantity INTEGER,
    unit_price NUMERIC(12,2),
    total NUMERIC(12,2)
);

CREATE INDEX idx_jobs_category ON jobs(category);
CREATE INDEX idx_jobs_location ON jobs(location);
CREATE INDEX idx_payments_user ON mobile_money_payments(user_id);
CREATE INDEX idx_income_user ON accounting_income(user_id);
CREATE INDEX idx_expense_user ON accounting_expenses(user_id);
CREATE INDEX idx_music_history_user ON music_history(user_id);
