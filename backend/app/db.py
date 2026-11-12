"""PostgreSQL storage.

* one connection per worker thread (autocommit), so request code can simply call `db.cursor()`
* SQL in this project uses `?` placeholders; they are converted to psycopg's `%s` here
* a tiny result cache, invalidated whenever data or settings change
"""

import json
import re
import threading
import time
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

-- POS integration (push API)
ALTER TABLE sales ADD COLUMN IF NOT EXISTS source TEXT;          -- NULL = file import, 'pos' = API
ALTER TABLE sales ADD COLUMN IF NOT EXISTS ext_key TEXT;         -- branch|invoice_no for API invoices
ALTER TABLE sales ADD COLUMN IF NOT EXISTS extra JSONB;
CREATE INDEX IF NOT EXISTS sales_ext_key_idx ON sales (ext_key) WHERE ext_key IS NOT NULL;
ALTER TABLE customer_directory ADD COLUMN IF NOT EXISTS registered_at TIMESTAMP;
ALTER TABLE customer_directory ADD COLUMN IF NOT EXISTS registered_branch TEXT;
ALTER TABLE customer_directory ADD COLUMN IF NOT EXISTS pos_customer_id TEXT;
ALTER TABLE customer_directory ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE customer_directory ADD COLUMN IF NOT EXISTS extra JSONB;
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    branch TEXT,                       -- default branch for invoices sent with this key
    prefix TEXT NOT NULL,              -- first characters, to recognise the key
    key_hash TEXT UNIQUE NOT NULL,     -- sha256 of the key (the key itself is never stored)
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT now(),
    last_used_at TIMESTAMP,
    requests BIGINT DEFAULT 0
);

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
        # psycopg only reads %-placeholders when parameters are passed
        self.cur.execute(sql(q) if params else q, params or None)
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


# who + day + amount: the lookup key of the duplicate check (see importer.DUP_MATCH)
MATCH_INDEX = """CREATE INDEX CONCURRENTLY IF NOT EXISTS sales_match_idx ON sales
    ((coalesce(phone, '~' || coalesce(branch, ''))), day, (round(item_price::numeric, 2)))"""


def _log(msg):
    print(f"[db] {msg}", flush=True)


def init():
    global _schema_ready
    with _schema_lock:
        if _schema_ready:
            return
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            # 1) queries left running by a previous app process (e.g. a killed import) would
            #    otherwise keep the CPU busy and block the schema check below
            n = conn.execute("""SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity
                WHERE datname = current_database() AND pid <> pg_backend_pid()
                  AND backend_type = 'client backend'
                  AND coalesce(application_name, '') NOT IN ('psql', 'pg_dump')""").fetchone()[0]
            if n:
                _log(f"stopped {n} query(ies) left over from before the restart")
            # 2) never hang at startup waiting for a lock
            conn.execute("SET lock_timeout = '15s'")
            for stmt in (x.strip() for x in re.split(r";[ \t]*(?:--[^\n]*)?\n", SCHEMA + "\n")):
                if not stmt or all(l.strip().startswith("--") for l in stmt.splitlines() if l.strip()):
                    continue
                try:
                    conn.execute(stmt)
                except psycopg.errors.LockNotAvailable:
                    _log(f"skipped (table busy): {stmt.splitlines()[0][:80]}")
            _seed_roles(Cursor(conn))
        _schema_ready = True
    threading.Thread(target=_build_indexes, daemon=True).start()


def _build_indexes():
    """Big indexes are built in the background without blocking the app or imports."""
    try:
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            bad = conn.execute("""SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = 'sales_match_idx' AND NOT i.indisvalid""").fetchone()
            if bad:  # an interrupted concurrent build leaves an invalid index behind
                conn.execute("DROP INDEX CONCURRENTLY IF EXISTS sales_match_idx")
            conn.execute(MATCH_INDEX)
    except Exception as e:  # noqa: BLE001 - only speeds things up
        _log(f"index build skipped: {e}")


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
    global _version, _last_bump, _pending_bump
    with _cache_lock:
        _version += 1
        _cache.clear()
        _last_bump = time.time()
        _pending_bump = False


_last_bump = 0.0
_pending_bump = False


def bump_version_soon(seconds: int = 60):
    """For live POS data: refresh cached reports at most once a minute (not on every sale)."""
    global _pending_bump
    if time.time() - _last_bump >= seconds:
        bump_version()
    else:
        _pending_bump = True


def cached(key, fn):
    """Cache analytics results until the next import / settings change."""
    if _pending_bump and time.time() - _last_bump >= 60:
        bump_version()
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
