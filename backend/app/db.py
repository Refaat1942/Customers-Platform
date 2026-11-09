"""PostgreSQL storage.

* one connection per worker thread (autocommit), so request code can simply call `db.cursor()`
* SQL in this project uses `?` placeholders; they are converted to psycopg's `%s` here
* a tiny result cache, invalidated whenever data or settings change
"""

import json
import re
import threading
from collections import OrderedDict

import psycopg
from psycopg.rows import tuple_row

from . import config

_local = threading.local()
_schema_lock = threading.Lock()
_schema_ready = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS roles (
    name TEXT PRIMARY KEY,
    description TEXT,
    permissions TEXT NOT NULL DEFAULT '[]',
    builtin BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'manager',
    branches TEXT NOT NULL DEFAULT '[]',        -- JSON list; empty = all branches
    language TEXT NOT NULL DEFAULT 'en',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS imports (
    id SERIAL PRIMARY KEY,
    filename TEXT,
    mode TEXT,
    status TEXT,                    -- running | done | failed | deleted
    stage TEXT,                     -- reading | cleaning | saving | finished
    progress DOUBLE PRECISION DEFAULT 0,
    message TEXT,
    sheet TEXT,
    file_hash TEXT,
    file_size BIGINT,
    mapping TEXT,
    rows_read BIGINT DEFAULT 0,
    rows_imported BIGINT DEFAULT 0,
    rows_skipped BIGINT DEFAULT 0,
    rows_replaced BIGINT DEFAULT 0,
    invalid_phones BIGINT DEFAULT 0,
    invalid_dates BIGINT DEFAULT 0,
    date_from DATE,
    date_to DATE,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT now(),
    finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sales (
    import_id INTEGER,
    phone TEXT,
    phone_valid BOOLEAN,
    name TEXT,
    branch TEXT,
    address TEXT,
    district TEXT,
    invoice_no TEXT,
    visit_key TEXT,
    invoice_date TIMESTAMP,
    day DATE,
    season TEXT,
    invoice_type TEXT,
    item_code TEXT,
    item_name TEXT,
    material_group TEXT,
    item_category TEXT,
    quantity DOUBLE PRECISION,
    item_unit TEXT,
    item_price DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS sales_day_idx ON sales (day);
CREATE INDEX IF NOT EXISTS sales_phone_idx ON sales (phone, day);
CREATE INDEX IF NOT EXISTS sales_branch_day_idx ON sales (branch, day);
CREATE INDEX IF NOT EXISTS sales_import_idx ON sales (import_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMP DEFAULT now(),
    username TEXT,
    action TEXT,
    details TEXT,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS audit_ts_idx ON audit_log (ts DESC);

-- customer lists from the CRM (one row per phone), linked to sales by phone
CREATE TABLE IF NOT EXISTS customer_directory (
    phone TEXT PRIMARY KEY,
    phone_valid BOOLEAN,
    name TEXT,
    first_name TEXT,
    last_name TEXT,
    address TEXT,
    region TEXT,
    city TEXT,
    district TEXT,
    area TEXT,
    email TEXT,
    gender TEXT,
    birth_date DATE,
    import_id INTEGER,
    updated_at TIMESTAMP DEFAULT now()
);
ALTER TABLE imports ADD COLUMN IF NOT EXISTS kind TEXT DEFAULT 'sales';

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS saved_mappings (signature TEXT PRIMARY KEY, mapping TEXT);
"""

_PLACEHOLDER = re.compile(r"\?")


def sql(q: str) -> str:
    """`?` -> `%s` (and escape literal % for psycopg)."""
    return _PLACEHOLDER.sub("%s", q.replace("%", "%%"))


class Cursor:
    """Small wrapper so the code can write `cur.execute(...).fetchone()` with `?` params."""

    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor(row_factory=tuple_row)

    def execute(self, q, params=None):
        self.cur.execute(sql(q), params or None)
        return self

    def fetchone(self):
        return self.cur.fetchone()

    def fetchall(self):
        return self.cur.fetchall()

    @property
    def description(self):
        return self.cur.description

    def copy(self, statement):
        return self.cur.copy(statement)


def _connect():
    conn = psycopg.connect(config.DATABASE_URL, autocommit=True)
    return conn


def connection():
    conn = getattr(_local, "conn", None)
    if conn is None or conn.closed or conn.broken:
        conn = _connect()
        _local.conn = conn
    return conn


def init():
    global _schema_ready
    with _schema_lock:
        if _schema_ready:
            return
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute(SCHEMA)
            _seed_roles(Cursor(conn))
        _schema_ready = True


def cursor() -> Cursor:
    return Cursor(connection())


def close():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


# ---------------------------------------------------------------- helpers
def rows(cur: Cursor, q, params=None):
    cur.execute(q, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def one(cur: Cursor, q, params=None):
    r = rows(cur, q, params)
    return r[0] if r else None


def get_settings(cur=None) -> dict:
    cur = cur or cursor()
    out = dict(config.DEFAULT_SETTINGS)
    for k, v in cur.execute("SELECT key, value FROM settings").fetchall():
        if k in out:
            out[k] = json.loads(v)
    return out


def public_settings(cur=None) -> dict:
    s = get_settings(cur)
    key = s.pop("openai_api_key", "") or ""
    s["openai_key_set"] = bool(key)
    s["openai_key_hint"] = f"...{key[-4:]}" if key else ""
    return s


def save_settings(values: dict, cur=None):
    cur = cur or cursor()
    for k, v in values.items():
        if k in config.DEFAULT_SETTINGS:
            cur.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT (key) "
                        "DO UPDATE SET value = EXCLUDED.value", [k, json.dumps(v)])
    bump_version()


def _seed_roles(cur):
    from .permissions import DEFAULT_ROLES
    for name, (desc, perms) in DEFAULT_ROLES.items():
        cur.execute("INSERT INTO roles VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    [name, desc, json.dumps(perms), name == "admin"])
    # admin always has every permission (also after an upgrade adds new ones)
    cur.execute("UPDATE roles SET permissions = ?, builtin = TRUE WHERE name = 'admin'",
                [json.dumps(DEFAULT_ROLES["admin"][1])])


def audit(username: str | None, action: str, details: str = "", ip: str | None = None):
    try:
        cursor().execute("INSERT INTO audit_log (username, action, details, ip) VALUES (?, ?, ?, ?)",
                         [username, action, (details or "")[:2000], ip])
    except Exception:  # noqa: BLE001 - never break a request because of logging
        pass


# ---------------------------------------------------------------- result cache
_cache: OrderedDict = OrderedDict()
_cache_lock = threading.Lock()
_version = 0
CACHE_SIZE = 300


def bump_version():
    global _version
    with _cache_lock:
        _version += 1
        _cache.clear()


def cached(key, fn):
    """Cache analytics results until the next import / settings change."""
    k = (_version, key)
    with _cache_lock:
        if k in _cache:
            _cache.move_to_end(k)
            return _cache[k]
    val = fn()
    with _cache_lock:
        _cache[k] = val
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return val
