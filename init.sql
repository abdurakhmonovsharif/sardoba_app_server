-- Idempotent SQL initialization script for Sardoba Cashback App
-- This script creates all tables if they do not already exist
-- Safe to run multiple times without errors

-- Create ENUM types (if not already created by previous runs)
DO $$ BEGIN
    CREATE TYPE staff_role AS ENUM ('MANAGER', 'WAITER');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE auth_actor_type AS ENUM ('CLIENT', 'STAFF');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE auth_action AS ENUM ('LOGIN', 'LOGOUT', 'OTP_REQUEST', 'OTP_VERIFICATION', 'FAILED_LOGIN');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE cashback_source AS ENUM ('QR', 'ORDER', 'MANUAL');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE user_level AS ENUM ('SILVER', 'GOLD', 'PREMIUM', 'VIP');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    ALTER TYPE user_level ADD VALUE IF NOT EXISTS 'VIP';
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Categories table
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) UNIQUE NOT NULL,
    image_url VARCHAR(500) NULL
);

-- Staff table
CREATE TABLE IF NOT EXISTS staff (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role staff_role NOT NULL DEFAULT 'WAITER',
    branch_id INTEGER NULL,
    referral_code VARCHAR(12) UNIQUE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_staff_phone ON staff(phone);
CREATE INDEX IF NOT EXISTS idx_staff_referral_code ON staff(referral_code);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NULL,
    surname VARCHAR(100) NULL,
    middle_name VARCHAR(100) NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    waiter_id INTEGER NULL REFERENCES staff(id),
    date_of_birth DATE NULL,
    profile_photo_url VARCHAR(512) NULL,
    level user_level NOT NULL DEFAULT 'SILVER',
    iiko_wallet_id VARCHAR(64) UNIQUE NULL,
    iiko_customer_id VARCHAR(64) UNIQUE NULL,
    pending_iiko_profile_update JSONB NULL,
    email VARCHAR(320) UNIQUE NULL,
    gender VARCHAR(16) NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    giftget BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
CREATE INDEX IF NOT EXISTS idx_users_waiter_id ON users(waiter_id);
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS surname VARCHAR(100) NULL;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS middle_name VARCHAR(100) NULL;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS pending_iiko_profile_update JSONB NULL;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS giftget BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS iiko_sync_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NULL,
    phone VARCHAR(20) NULL,
    operation VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    payload JSONB NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 8,
    next_retry_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    last_attempt_at TIMESTAMP WITH TIME ZONE NULL,
    completed_at TIMESTAMP WITH TIME ZONE NULL,
    lock_owner VARCHAR(64) NULL,
    locked_at TIMESTAMP WITH TIME ZONE NULL,
    last_error TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_iiko_sync_jobs_status_next_retry_at
ON iiko_sync_jobs(status, next_retry_at);
CREATE INDEX IF NOT EXISTS ix_iiko_sync_jobs_user_operation
ON iiko_sync_jobs(user_id, operation);
CREATE INDEX IF NOT EXISTS ix_iiko_sync_jobs_user_id
ON iiko_sync_jobs(user_id);
CREATE INDEX IF NOT EXISTS ix_iiko_sync_jobs_phone
ON iiko_sync_jobs(phone);

CREATE TABLE IF NOT EXISTS deleted_phones (
    id SERIAL PRIMARY KEY,
    real_phone VARCHAR(20) NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    user_id INTEGER NULL REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_deleted_phones_real_phone ON deleted_phones(real_phone);
CREATE INDEX IF NOT EXISTS idx_deleted_phones_user_id ON deleted_phones(user_id);

-- Cashback balances table
CREATE TABLE IF NOT EXISTS cashback_balances (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    balance NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    points NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Cards table
CREATE TABLE IF NOT EXISTS cards (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_number VARCHAR(32) UNIQUE NOT NULL,
    card_track VARCHAR(64) UNIQUE NOT NULL,
    iiko_card_id VARCHAR(64) NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cards_user_id ON cards(user_id);

-- Cashback transactions table
CREATE TABLE IF NOT EXISTS cashback_transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    staff_id INTEGER NULL REFERENCES staff(id),
    amount NUMERIC(12, 2) NOT NULL,
    branch_id INTEGER NULL,
    source cashback_source NOT NULL,
    balance_after NUMERIC(12, 2) NOT NULL,
    iiko_event_id VARCHAR(128) UNIQUE NULL,
    iiko_uoc_id VARCHAR(128) NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cashback_transactions_user_id ON cashback_transactions(user_id);
ALTER TABLE IF EXISTS cashback_transactions ADD COLUMN IF NOT EXISTS iiko_uoc_id VARCHAR(128) NULL;

-- OTP codes table
CREATE TABLE IF NOT EXISTS otp_codes (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    code VARCHAR(10) NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    ip VARCHAR(45) NULL,
    user_agent VARCHAR(255) NULL
);

CREATE INDEX IF NOT EXISTS idx_otp_codes_phone ON otp_codes(phone);
CREATE INDEX IF NOT EXISTS idx_otp_codes_code ON otp_codes(code);
CREATE INDEX IF NOT EXISTS idx_otp_codes_ip ON otp_codes(ip);

-- Auth logs table
CREATE TABLE IF NOT EXISTS auth_logs (
    id SERIAL PRIMARY KEY,
    actor_type auth_actor_type NOT NULL DEFAULT 'CLIENT',
    actor_id INTEGER NULL,
    phone VARCHAR(20) NULL,
    action auth_action NOT NULL DEFAULT 'LOGIN',
    ip VARCHAR(45) NULL,
    user_agent VARCHAR(255) NULL,
    meta JSONB NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notification_device_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_token VARCHAR(255) UNIQUE,
    device_type VARCHAR(16) NOT NULL,
    language VARCHAR(8) NOT NULL DEFAULT 'ru',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notification_device_tokens_user_id ON notification_device_tokens(user_id);

CREATE TABLE IF NOT EXISTS user_notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_id INTEGER REFERENCES notifications(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    type VARCHAR(64),
    payload JSONB NULL,
    language VARCHAR(8) NOT NULL DEFAULT 'ru',
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    is_sent BOOLEAN NOT NULL DEFAULT FALSE,
    sent_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_notifications_user_id ON user_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_user_notifications_notification_id ON user_notifications(notification_id);

-- News table
CREATE TABLE IF NOT EXISTS news (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    image_url VARCHAR(500) NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    starts_at TIMESTAMP WITH TIME ZONE NULL,
    ends_at TIMESTAMP WITH TIME ZONE NULL,
    priority INTEGER NOT NULL DEFAULT 0
);

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    name VARCHAR(255) NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    image_url VARCHAR(500) NULL
);

CREATE INDEX IF NOT EXISTS idx_products_category_id ON products(category_id);
