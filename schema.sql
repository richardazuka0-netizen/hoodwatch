PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS raw_logs (
    chain_id INTEGER NOT NULL,
    tx TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    address TEXT NOT NULL,
    block INTEGER NOT NULL,
    topic0 TEXT,
    data TEXT,
    topics_json TEXT,
    PRIMARY KEY (chain_id, tx, log_index)
);

CREATE TABLE IF NOT EXISTS launches (
    id TEXT PRIMARY KEY,
    generation TEXT NOT NULL,
    factory TEXT NOT NULL,
    launch_id TEXT NOT NULL,
    token TEXT NOT NULL,
    curve TEXT NOT NULL,
    creator TEXT NOT NULL,
    creator_fee_recipient TEXT NOT NULL,
    creator_vault TEXT NOT NULL,
    quote_currency TEXT,
    block INTEGER NOT NULL,
    tx TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    graduation_target_wei TEXT,
    initial_buy_wei TEXT,
    initial_tokens_bought TEXT,
    graduated INTEGER NOT NULL DEFAULT 0,
    graduation_block INTEGER,
    graduation_tx TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    launch_id TEXT NOT NULL,
    token TEXT NOT NULL,
    curve TEXT NOT NULL,
    wallet TEXT NOT NULL,
    role TEXT NOT NULL,
    side TEXT NOT NULL,
    buyer TEXT,
    recipient TEXT,
    token_amount TEXT NOT NULL,
    quote_amount TEXT NOT NULL,
    gross_amount TEXT NOT NULL,
    block INTEGER NOT NULL,
    tx TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    log_index INTEGER NOT NULL,
    UNIQUE (launch_id, tx, log_index, wallet, role)
);

CREATE TABLE IF NOT EXISTS scan_cursor (
    generation TEXT PRIMARY KEY,
    last_block INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS funding (
    from_wallet TEXT NOT NULL,
    to_wallet TEXT NOT NULL,
    value_wei TEXT NOT NULL,
    block INTEGER NOT NULL,
    tx TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    PRIMARY KEY (from_wallet, to_wallet, block, tx, log_index)
);

CREATE TABLE IF NOT EXISTS wallet_tags (
    wallet TEXT NOT NULL,
    tag TEXT NOT NULL,
    rate REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (wallet, tag)
);

CREATE TABLE IF NOT EXISTS tag_evidence (
    wallet TEXT NOT NULL,
    tag TEXT NOT NULL,
    token TEXT NOT NULL,
    tx TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    PRIMARY KEY (wallet, tag, token, tx, reason_code)
);

CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    method TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cluster_members (
    cluster_id INTEGER NOT NULL,
    wallet TEXT NOT NULL,
    PRIMARY KEY (cluster_id, wallet)
);

CREATE TABLE IF NOT EXISTS cluster_edges (
    cluster_id INTEGER NOT NULL,
    from_wallet TEXT NOT NULL,
    to_wallet TEXT NOT NULL,
    reason TEXT NOT NULL,
    weight INTEGER NOT NULL,
    PRIMARY KEY (cluster_id, from_wallet, to_wallet, reason)
);

CREATE TABLE IF NOT EXISTS follows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_viewed_at TEXT,
    UNIQUE (subject_type, subject_id)
);

CREATE INDEX IF NOT EXISTS idx_launches_block
    ON launches (block);

CREATE INDEX IF NOT EXISTS idx_trades_wallet
    ON trades (wallet);

CREATE INDEX IF NOT EXISTS idx_trades_token_block
    ON trades (token, block);

CREATE INDEX IF NOT EXISTS idx_tag_evidence_wallet
    ON tag_evidence (wallet);
