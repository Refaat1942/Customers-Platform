"""DuckDB storage. One process-wide connection; each request uses its own cursor."""

import json
import threading

import duckdb

from . import config

_con = None
_lock = threading.Lock()

SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS seq_users START 1;
CREATE SEQUENCE IF NOT EXISTS seq_imports START 1;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY DEFAULT nextval('seq_users'),
    username VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    full_name VARCHAR,
    role VARCHAR NOT NULL DEFAULT 'manager',      -- admin | manager
    branches VARCHAR NOT NULL DEFAULT '[]',        -- JSON list; empty = all branches
    language VARCHAR NOT NULL DEFAULT 'en',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY DEFAULT nextval('seq_imports'),
    filename VARCHAR,
    mode VARCHAR,
    status VARCHAR,                 -- running | done | failed | deleted
    message VARCHAR,
    mapping VARCHAR,
    rows_read BIGINT DEFAULT 0,
    rows_imported BIGINT DEFAULT 0,
    rows_skipped BIGINT DEFAULT 0,
    rows_replaced BIGINT DEFAULT 0,
    invalid_phones BIGINT DEFAULT 0,
    invalid_dates BIGINT DEFAULT 0,
    date_from DATE,
    date_to DATE,
    created_by VARCHAR,
    created_at TIMESTAMP DEFAULT current_timestamp,
    finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sales (
    import_id INTEGER,
    phone VARCHAR,
    phone_valid BOOLEAN,
    name VARCHAR,
    branch VARCHAR,
    address VARCHAR,
    district VARCHAR,
    invoice_no VARCHAR,
    visit_key VARCHAR,
    invoice_date TIMESTAMP,
    day DATE,
    season VARCHAR,
    invoice_type VARCHAR,
    item_code VARCHAR,
    item_name VARCHAR,
    material_group VARCHAR,
    item_category VARCHAR,
    quantity DOUBLE,
    item_unit VARCHAR,
    item_price DOUBLE
);

CREATE TABLE IF NOT EXISTS settings (key VARCHAR PRIMARY KEY, value VARCHAR);
CREATE TABLE IF NOT EXISTS saved_mappings (signature VARCHAR PRIMARY KEY, mapping VARCHAR);
"""


def connect():
    global _con
    with _lock:
        if _con is None:
            _con = duckdb.connect(str(config.DB_PATH))
            _con.execute(SCHEMA)
    return _con


def cursor():
    return connect().cursor()


def close():
    global _con
    with _lock:
        if _con is not None:
            _con.close()
            _con = None


# ---------------------------------------------------------------- helpers
def rows(cur, sql, params=None):
    res = cur.execute(sql, params or [])
    cols = [d[0] for d in res.description]
    return [dict(zip(cols, r)) for r in res.fetchall()]


def one(cur, sql, params=None):
    r = rows(cur, sql, params)
    return r[0] if r else None


def get_settings(cur=None) -> dict:
    cur = cur or cursor()
    out = dict(config.DEFAULT_SETTINGS)
    for k, v in cur.execute("SELECT key, value FROM settings").fetchall():
        if k in out:
            out[k] = json.loads(v)
    return out


def save_settings(values: dict, cur=None):
    cur = cur or cursor()
    for k, v in values.items():
        if k in config.DEFAULT_SETTINGS:
            cur.execute(
                "INSERT OR REPLACE INTO settings VALUES (?, ?)", [k, json.dumps(v)]
            )
