CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    nickname VARCHAR(100) NOT NULL,
    password_hash TEXT NOT NULL,
    language VARCHAR(20) NOT NULL,
    visa_type VARCHAR(50) NOT NULL,
    nationality VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_users_email ON users (email);
CREATE UNIQUE INDEX idx_users_nickname ON users (nickname);

CREATE TABLE cards (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    stay_qualification VARCHAR(100) NOT NULL,
    registration_number_encrypted TEXT NOT NULL,
    stay_address TEXT NOT NULL,
    stay_start_date DATE NOT NULL,
    stay_end_date DATE NOT NULL,
    passport_number_encrypted TEXT NOT NULL,
    passport_expires_on DATE NOT NULL,
    registration_front_image_url TEXT NOT NULL,
    registration_back_image_url TEXT NOT NULL,
    passport_image_url TEXT NOT NULL,
    account_purposes TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cards_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX idx_cards_user_id ON cards (user_id);

CREATE TABLE account_opening_applications (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    s3_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_account_opening_applications_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_account_opening_applications_user_id
    ON account_opening_applications (user_id);

CREATE TABLE integrated_applications (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    s3_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_integrated_applications_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_integrated_applications_user_id
    ON integrated_applications (user_id);
