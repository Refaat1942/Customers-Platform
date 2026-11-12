"""Excel/CSV import: read -> map columns -> clean -> store in `sales`."""

import hashlib
import json
import shutil
import threading
import zipfile
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from python_calamine import CalamineWorkbook

import psycopg

from .. import config, db
from .address import extract_district
from .columns import (CUSTOMER_FIELDS, CUSTOMER_REQUIRED, FIELDS, REQUIRED_FIELDS,
                      clean_col_name, find_columns, find_customer_columns)
from .phone import is_valid_egy_mobile, normalize_egy_phone

SEASONS = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
           6: "Summer", 7: "Summer", 8: "Summer", 9: "Autumn", 10: "Autumn", 11: "Autumn"}

IMPORT_MODES = ("merge", "replace_period", "append_new", "replace_all")
CUSTOMER_MODES = ("upsert", "replace_all")

TEXT_FIELDS = ["name", "branch", "address", "district", "invoice_no", "invoice_type",
               "item_code", "item_name", "material_group", "item_category", "item_unit"]


# ---------------------------------------------------------------- reading
EXCEL_SUFFIXES = (".xlsx", ".xlsm", ".xls", ".xlsb")
CHUNK_ROWS = 100_000


def unpack(path: Path) -> Path:
    """Large files are often zipped (10x smaller upload). Extract the first Excel/CSV inside."""
    if path.suffix.lower() != ".zip":
        return path
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if Path(n).suffix.lower() in EXCEL_SUFFIXES + (".csv",)
                 and not n.startswith("__MACOSX")]
        if not names:
            raise ValueError("The zip file has no Excel or CSV file inside")
        target = path.with_name(path.stem + "_unzipped" + Path(names[0]).suffix.lower())
        with z.open(names[0]) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
    path.unlink(missing_ok=True)
    return target


def sheet_names(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        return []
    return CalamineWorkbook.from_path(str(path)).sheet_names


def _csv_encoding(path: Path) -> str:
    with path.open("rb") as fh:
        sample = fh.read(1024 * 1024)
    for enc in ("utf-8-sig", "cp1256"):
        try:
            sample.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _csv_reader(path: Path, nrows=None, chunksize=None):
    enc = _csv_encoding(path)
    with path.open(encoding=enc, errors="replace") as fh:
        head = fh.readline()
    sep = max([",", ";", "\t", "|"], key=head.count)
    return pd.read_csv(path, nrows=nrows, chunksize=chunksize, dtype=object, encoding=enc,
                       sep=sep, encoding_errors="replace")


def _clean_header(cols) -> list[str]:
    out, seen = [], {}
    for i, c in enumerate(cols):
        c = str(c).strip() if c not in (None, "") else f"Column {i + 1}"
        if c in seen:
            seen[c] += 1
            c = f"{c} ({seen[c]})"
        else:
            seen[c] = 0
        out.append(c)
    return out


def iter_chunks(path: Path, sheet: str | None = None, chunk_rows=CHUNK_ROWS):
    """Yield (DataFrame chunk, estimated total rows). Never loads a CSV fully in memory."""
    if path.suffix.lower() == ".csv":
        with path.open("rb") as fh:
            sample = fh.read(4 * 1024 * 1024)
        bytes_per_row = len(sample) / max(sample.count(b"\n"), 1)
        total = int(path.stat().st_size / max(bytes_per_row, 1))
        for chunk in _csv_reader(path, chunksize=chunk_rows):
            chunk.columns = _clean_header(chunk.columns)
            yield chunk, total
        return

    wb = CalamineWorkbook.from_path(str(path))
    sh = wb.get_sheet_by_name(sheet or wb.sheet_names[0])
    total = max(sh.total_height - 1, 0)
    it = sh.iter_rows()
    header = None
    for row in it:  # first non-empty row is the header
        if any(v not in (None, "") for v in row):
            header = _clean_header(row)
            break
    if header is None:
        return
    buf = []
    for row in it:
        buf.append(row)
        if len(buf) >= chunk_rows:
            yield pd.DataFrame(buf, columns=header), total
            buf = []
    if buf:
        yield pd.DataFrame(buf, columns=header), total


def read_file(path: Path, nrows=None, sheet: str | None = None) -> pd.DataFrame:
    """Small reads (preview, tests)."""
    if path.suffix.lower() == ".csv":
        df = _csv_reader(path, nrows=nrows)
        df.columns = _clean_header(df.columns)
        return df
    wb = CalamineWorkbook.from_path(str(path))
    sh = wb.get_sheet_by_name(sheet or wb.sheet_names[0])
    data = sh.to_python(nrows=(nrows + 5) if nrows else None)
    data = [r for r in data if any(v not in (None, "") for v in r)]
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data[1:], columns=_clean_header(data[0]))
    return df.head(nrows) if nrows else df


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def header_signature(columns, kind: str = "sales") -> str:
    key = kind + ":" + "|".join(sorted(clean_col_name(c) for c in columns))
    return hashlib.sha1(key.encode()).hexdigest()


# ---------------------------------------------------------------- smart detection
def profile_columns(df: pd.DataFrame) -> dict:
    """Look at the VALUES of each column: how many look like phones, dates, money, ..."""
    out = {}
    for c in df.columns:
        s = df[c].dropna()
        s = s[s.astype(str).str.strip() != ""]
        n = len(s)
        if n == 0:
            out[c] = {"n": 0, "phone": 0, "date": 0, "num": 0, "decimal": 0, "unique": 0}
            continue
        txt = s.astype(str)
        phone = txt.map(lambda v: is_valid_egy_mobile(normalize_egy_phone(v))).mean()
        dates = _parse_dates(s.astype(object))
        date_ratio = dates.notna().mean()
        if date_ratio:  # plain numbers like 1500 are not dates unless the column really is
            years = dates.dropna().dt.year
            date_ratio *= float(years.between(2000, 2100).mean())
            if pd.api.types.is_numeric_dtype(s) or txt.str.fullmatch(r"\d+(\.\d+)?").mean() > 0.8:
                date_ratio *= float(pd.to_numeric(s, errors="coerce").between(30000, 60000).mean())
        num = _parse_numbers(s)
        out[c] = {"n": n, "phone": float(phone), "date": float(date_ratio),
                  "num": float(num.notna().mean()),
                  "decimal": float(((num.dropna() % 1) != 0).mean()) if num.notna().any() else 0.0,
                  "unique": float(s.nunique() / n)}
    return out


PRICE_HINTS = ("price", "amount", "total", "net", "value", "sales", "revenue", "قيمة", "سعر",
               "اجمالي", "إجمالي", "egp", "rsp")


def smart_sales_mapping(df: pd.DataFrame, mapping: dict, prof: dict) -> dict:
    """Fix / complete the header-based guess using the column values."""
    m = dict(mapping)
    used = {v for v in m.values() if v}

    def best(metric, min_ratio, exclude=()):
        cands = [(p[metric], c) for c, p in prof.items()
                 if c not in used and c not in exclude and p["n"] and p[metric] >= min_ratio]
        return max(cands)[1] if cands else None

    # phone: header guess must actually contain phone numbers
    if m.get("phone") and prof.get(m["phone"], {}).get("phone", 0) < 0.3:
        better = best("phone", 0.6)
        if better:
            used.discard(m["phone"])
            m["phone"] = better
    if not m.get("phone"):
        m["phone"] = best("phone", 0.6)
        used.add(m["phone"])

    if m.get("invoice_date") and prof.get(m["invoice_date"], {}).get("date", 0) < 0.5:
        used.discard(m["invoice_date"])
        m["invoice_date"] = None
    if not m.get("invoice_date"):
        m["invoice_date"] = best("date", 0.7)
        used.add(m["invoice_date"])

    if m.get("item_price") and prof.get(m["item_price"], {}).get("num", 0) < 0.7:
        used.discard(m["item_price"])
        m["item_price"] = None
    if not m.get("item_price"):
        cands = []
        for c, p in prof.items():
            if c in used or not p["n"] or p["num"] < 0.9 or p["phone"] > 0.3 or p["date"] > 0.3:
                continue
            name = clean_col_name(c)
            score = p["decimal"] + (1 if any(h in name for h in PRICE_HINTS) else 0) \
                - (1 if any(h in name for h in ("code", "id", "no", "number", "qty", "كود")) else 0)
            cands.append((score, c))
        if cands and max(cands)[0] > 0:
            m["item_price"] = max(cands)[1]
    used.discard(None)
    return m


def detect_kind(sales_map: dict, cust_map: dict) -> tuple[str, str]:
    """('sales' | 'customers', reason)."""
    if sales_map.get("invoice_date") and sales_map.get("item_price") and sales_map.get("phone"):
        return "sales", "dates_amounts"
    has_details = any(cust_map.get(k) for k in ("name", "first_name", "address", "city",
                                                 "district", "area", "region"))
    if cust_map.get("phone") and has_details:
        return "customers", "no_dates_amounts"
    return "sales", "unknown"


def suggest_mappings(columns, df: pd.DataFrame) -> dict:
    """Saved mapping for this header layout if any, else the smart guess, for both kinds."""
    cur = db.cursor()
    prof = profile_columns(df)
    out = {}
    for kind, guess in (("sales", lambda: smart_sales_mapping(df, find_columns(columns), prof)),
                        ("customers", lambda: find_customer_columns(columns))):
        fields = FIELDS if kind == "sales" else CUSTOMER_FIELDS
        saved = db.one(cur, "SELECT mapping FROM saved_mappings WHERE signature = ?",
                       [header_signature(columns, kind)])
        if saved:
            mm = json.loads(saved["mapping"])
            out[kind] = {f: (mm.get(f) if mm.get(f) in columns else None) for f in fields}
        else:
            out[kind] = guess()
    if out["customers"].get("phone") is None and out["sales"].get("phone"):
        out["customers"]["phone"] = out["sales"]["phone"]
    return out


def _jsonable(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v if isinstance(v, (int, float, bool)) else str(v)


def analyse_sheet(path: Path, sheet: str | None) -> dict:
    """Read the first rows of one sheet and decide what it is and how its columns map."""
    df = read_file(path, nrows=300, sheet=sheet)
    df = df.dropna(axis=1, how="all")
    cols = list(df.columns)
    if df.empty or not cols:
        return {"sheet": sheet, "kind": "empty", "kind_reason": "empty", "columns": cols,
                "mappings": {"sales": {}, "customers": {}}, "mapping": {}, "sample": [], "rows": 0}
    maps = suggest_mappings(cols, df)
    kind, reason = detect_kind(maps["sales"], maps["customers"])
    if reason == "unknown":
        kind = "skip"
    return {"sheet": sheet, "kind": kind, "kind_reason": reason, "columns": cols,
            "mappings": maps, "mapping": maps.get(kind, maps["sales"]),
            "sample": [{c: _jsonable(v) for c, v in r.items()} for r in df.head(10).to_dict("records")]}


def preview(path: Path, sheet: str | None = None) -> dict:
    """Analyse every sheet of the workbook (or the CSV) - each can be a different kind of data."""
    names = sheet_names(path)
    totals = {}
    if names:
        wb = CalamineWorkbook.from_path(str(path))
        for n in names:
            try:
                totals[n] = max(wb.get_sheet_by_name(n).total_height - 1, 0)
            except Exception:  # noqa: BLE001
                totals[n] = None
    targets = ([sheet] if sheet else names[:30]) if names else [None]
    sheets = []
    for n in targets:
        info = analyse_sheet(path, n)
        info["rows"] = totals.get(n) if n else None
        sheets.append(info)
    first = next((x for x in sheets if x["kind"] in ("sales", "customers")), sheets[0])
    return {
        "sheets": names,
        "sheets_info": sheets,
        # the first useful sheet, for single-sheet callers
        "sheet": first["sheet"], "columns": first["columns"], "kind": first["kind"],
        "kind_reason": first["kind_reason"], "mappings": first["mappings"],
        "mapping": first["mapping"], "sample": first["sample"],
        "fields": {"sales": FIELDS, "customers": CUSTOMER_FIELDS},
        "required": {"sales": REQUIRED_FIELDS, "customers": CUSTOMER_REQUIRED},
        "modes": {"sales": list(IMPORT_MODES), "customers": list(CUSTOMER_MODES)},
    }


_import_lock = threading.Lock()
_cancelled: set[int] = set()


class Cancelled(Exception):
    pass


def log(msg: str):
    print(f"[import] {datetime.now():%H:%M:%S} {msg}", flush=True)


def cancel(import_id: int):
    """Ask a queued or running import to stop (checked between batches)."""
    _cancelled.add(import_id)


def _check_cancel(import_id: int):
    if import_id in _cancelled:
        raise Cancelled("Cancelled by user")


def run_jobs(jobs: list[dict], path: Path):
    """Run several sheet imports from the same file one after another, then delete the file.
    Imports of different files wait for each other (one import at a time = no collisions)."""
    ids = [j["import_id"] for j in jobs]
    log(f"queued {ids}")
    try:
        _import_lock.acquire()
        # customer lists first, so the sales imported next get names/districts from them
        for j in sorted(jobs, key=lambda j: 0 if j["kind"] == "customers" else 1):
            if j["import_id"] in _cancelled:
                db.cursor().execute("UPDATE imports SET status='failed', message='Cancelled by user', "
                                    "finished_at=now() WHERE id=? AND status='running'", [j["import_id"]])
                continue
            fn = run_customer_import if j["kind"] == "customers" else run_import
            log(f"#{j['import_id']} started ({j['kind']}, sheet={j['sheet']}, mode={j['mode']})")
            fn(j["import_id"], path, j["mapping"], j["mode"], j["sheet"], cleanup=False)
            st = db.one(db.cursor(), "SELECT status, message, rows_imported, rows_skipped FROM imports "
                                     "WHERE id = ?", [j["import_id"]]) or {}
            log(f"#{j['import_id']} {st.get('status')}: imported={st.get('rows_imported')} "
                f"skipped={st.get('rows_skipped')} {st.get('message') or ''}")
    finally:
        _import_lock.release()
        for i in ids:
            _cancelled.discard(i)
        path.unlink(missing_ok=True)
    warm_cache_soon()


# ---------------------------------------------------------------- cleaning
def _ns(v: pd.Series) -> pd.Series:
    """Keep plausible dates only and store them in one resolution (avoids pandas unit clashes)."""
    v = pd.to_datetime(v, errors="coerce")
    v = v.where((v.dt.year >= 1900) & (v.dt.year <= 2200))
    return v.astype("datetime64[ns]")


def _parse_dates(s: pd.Series) -> pd.Series:
    """Excel datetimes, Excel serial numbers, ISO text (yyyy-mm-dd) and Egyptian dd/mm/yyyy text."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return _ns(s)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")

    is_dt = s.map(lambda v: isinstance(v, (datetime, date)))
    if is_dt.any():
        out[is_dt] = _ns(s[is_dt].map(pd.Timestamp))

    rest = ~is_dt & s.notna()
    num = pd.to_numeric(s[rest], errors="coerce")
    serial = num.between(20000, 80000)  # Excel serial day numbers
    if serial.any():
        idx = num[serial].index
        out[idx] = _ns(pd.to_datetime(num[serial], unit="D", origin="1899-12-30"))
        rest[idx] = False
    rest &= ~pd.Series(num.notna(), index=num.index).reindex(s.index, fill_value=False)

    if rest.any():
        txt = s[rest].astype(str).str.strip()
        iso = txt.str.match(r"^\d{4}-\d{1,2}-\d{1,2}")
        if iso.any():
            out[txt[iso].index] = _ns(pd.to_datetime(txt[iso], errors="coerce", format="ISO8601"))
        if (~iso).any():
            out[txt[~iso].index] = _ns(pd.to_datetime(txt[~iso], errors="coerce", dayfirst=True,
                                                      format="mixed"))
    return out


def _parse_numbers(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    cleaned = (s.astype(str).str.replace(",", "", regex=False)
               .str.replace("EGP", "", regex=False).str.strip())
    return pd.to_numeric(cleaned, errors="coerce")


def _text(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)  # 101.0 -> "101" (codes stored as numbers in Excel)
    s = str(v).strip()
    return s or None


def _clean_text(s: pd.Series) -> pd.Series:
    return s.astype(object).map(_text)


def build_frame(raw: pd.DataFrame, mapping: dict) -> tuple[pd.DataFrame, dict]:
    """Return the canonical sales frame + stats about dropped / fixed rows."""
    stats = {"rows_read": len(raw), "invalid_dates": 0, "invalid_phones": 0}
    out = pd.DataFrame(index=raw.index)

    def src(field):
        c = mapping.get(field)
        return raw[c] if c and c in raw.columns else None

    # phone (normalise unique values only - fast on big files)
    ph = src("phone")
    uniq = {v: normalize_egy_phone(v) for v in pd.unique(ph.astype(str))}
    out["phone"] = ph.astype(str).map(uniq).map(lambda v: v or None).astype(object)
    out["phone_valid"] = out["phone"].map(is_valid_egy_mobile)
    stats["invalid_phones"] = int((out["phone"].notna() & ~out["phone_valid"]).sum())

    out["invoice_date"] = _parse_dates(src("invoice_date"))
    out["item_price"] = _parse_numbers(src("item_price")).fillna(0.0)
    q = src("quantity")
    out["quantity"] = _parse_numbers(q) if q is not None else np.nan

    for f in TEXT_FIELDS:
        s = src(f)
        out[f] = _clean_text(s) if s is not None else None

    if mapping.get("district") is None:
        if mapping.get("address"):
            addr = out["address"]
            uniq = {v: extract_district(v) for v in pd.unique(addr.dropna())}
            out["district"] = addr.map(uniq).fillna("Unknown")
        else:
            out["district"] = "Unknown"
    else:
        out["district"] = out["district"].fillna("Unknown")

    bad_date = out["invoice_date"].isna()
    stats["invalid_dates"] = int(bad_date.sum())
    out = out[~bad_date].copy()

    out["day"] = out["invoice_date"].dt.normalize()
    out["season"] = out["invoice_date"].dt.month.map(SEASONS)
    fallback_key = (out["phone"].fillna("?") + "|" + out["day"].dt.strftime("%Y-%m-%d")
                    + "|" + out["branch"].fillna("").astype(str))
    out["visit_key"] = out["invoice_no"].where(out["invoice_no"].notna(), fallback_key)
    return out, stats


# ---------------------------------------------------------------- duplicates
# A new line `s` is a duplicate of an existing line `x` when it's the same customer (or the same
# branch for walk-in sales), the same day and time (a date without a time matches any time that day),
# the same amount and quantity, and the same product by code OR by name.
# Lookup by (customer or branch, day, amount) - indexed by db.MATCH_INDEX, so even a phone with
# thousands of lines a day is checked instantly - then the tolerant comparison on the rest.
DUP_MATCH = """EXISTS (SELECT 1 FROM sales x
    WHERE coalesce(x.phone, '~' || coalesce(x.branch, '')) = coalesce(s.phone, '~' || coalesce(s.branch, ''))
      AND x.day = s.day
      AND round(x.item_price::numeric, 2) = round(s.item_price::numeric, 2)
      AND (x.invoice_date = s.invoice_date OR x.invoice_date::time = '00:00'
           OR s.invoice_date::time = '00:00')
      AND (x.quantity IS NOT DISTINCT FROM s.quantity OR x.quantity IS NULL OR s.quantity IS NULL)
      AND (x.item_code = s.item_code OR x.item_name = s.item_name
           OR (x.item_code IS NULL AND x.item_name IS NULL
               AND s.item_code IS NULL AND s.item_name IS NULL)))"""


# Exact duplicates already stored by DIFFERENT imports (same file uploaded twice, overlapping
# reports). Rows of the first import are kept - including legitimate repeated lines inside it.
DUP_FINGERPRINT = """coalesce(phone, '~' || coalesce(branch, '')), invoice_date,
    round(item_price::numeric, 2), quantity, coalesce(item_code, item_name, '')"""


def find_duplicates(cur) -> dict:
    r = cur.execute(f"""WITH r AS (
          SELECT import_id, dense_rank() OVER (PARTITION BY {DUP_FINGERPRINT}
                                               ORDER BY coalesce(import_id, 0)) AS dr
          FROM sales WHERE source IS DISTINCT FROM 'pos')
        SELECT count(*) FILTER (WHERE dr > 1), count(DISTINCT import_id) FILTER (WHERE dr > 1)
        FROM r""").fetchone()
    return {"duplicate_lines": r[0], "imports_affected": r[1]}


def remove_duplicates(conn) -> int:
    cur = db.Cursor(conn)
    with conn.transaction():
        n = cur.execute(f"""WITH r AS (
              SELECT ctid, dense_rank() OVER (PARTITION BY {DUP_FINGERPRINT}
                                              ORDER BY coalesce(import_id, 0)) AS dr
              FROM sales WHERE source IS DISTINCT FROM 'pos')
            DELETE FROM sales WHERE ctid IN (SELECT ctid FROM r WHERE dr > 1)""").cur.rowcount
    cur.execute("ANALYZE sales")
    db.bump_version()
    return n


# ---------------------------------------------------------------- running
SALES_COLS = ["import_id", "phone", "phone_valid", "name", "branch", "address", "district",
              "invoice_no", "visit_key", "invoice_date", "day", "season", "invoice_type",
              "item_code", "item_name", "material_group", "item_category", "quantity",
              "item_unit", "item_price"]


def _progress(cur, import_id, stage, pct, **extra):
    sets = ", ".join(["stage=?", "progress=?"] + [f"{k}=?" for k in extra])
    cur.execute(f"UPDATE imports SET {sets} WHERE id=?",
                [stage, round(pct, 1), *extra.values(), import_id])


def _copy_frame(cur, table: str, frame: pd.DataFrame):
    """Bulk load with PostgreSQL COPY (much faster than INSERTs)."""
    obj = frame.astype(object).where(frame.notna(), None)
    with cur.copy(f"COPY {table} ({', '.join(SALES_COLS)}) FROM STDIN") as cp:
        for row in obj.itertuples(index=False, name=None):
            cp.write_row(row)


_warming = threading.Lock()


def warm_cache_soon():
    """Pre-compute the dashboard in the background - never while holding up the import queue."""
    def run():
        if not _warming.acquire(blocking=False):
            return
        try:
            if not _import_lock.locked():  # another import started: it will warm when done
                _warm_cache()
        finally:
            _warming.release()
    threading.Thread(target=run, daemon=True).start()


def _warm_cache():
    """Pre-compute the default dashboard so the first page view after an import is instant."""
    from . import analytics as an
    try:
        f, s = an.Filters(), db.get_settings()
        db.cached(("summary", f.key()), lambda: an.summary(f, s))
        db.cached(("insights", f.key()), lambda: an.insights(f, s))
    except Exception:  # noqa: BLE001 - only an optimisation
        pass


def run_import(import_id: int, path: Path, mapping: dict, mode: str, sheet: str | None = None,
               cleanup: bool = True):
    """Stream the file in 100k-row chunks into a staging table, then swap it in atomically."""
    conn = psycopg.connect(config.DATABASE_URL, autocommit=True)
    cur = db.Cursor(conn)
    stage_tbl = f"staging_{import_id}"
    try:
        stats = {"rows_read": 0, "invalid_dates": 0, "invalid_phones": 0}
        cur.execute(f"DROP TABLE IF EXISTS {stage_tbl}")
        cur.execute(f"CREATE UNLOGGED TABLE {stage_tbl} (LIKE sales)")
        _progress(cur, import_id, "reading", 1)

        checked = False
        for chunk, total in iter_chunks(path, sheet):
            if not checked:
                missing = [f for f in REQUIRED_FIELDS
                           if not mapping.get(f) or mapping[f] not in chunk.columns]
                if missing:
                    raise ValueError(f"Missing required columns: {', '.join(missing)}")
                checked = True
            _check_cancel(import_id)
            frame, st = build_frame(chunk, mapping)
            for k in stats:
                stats[k] += st[k]
            _copy_frame(cur, stage_tbl, frame.assign(import_id=import_id)[SALES_COLS])
            pct = 5 + 85 * min(stats["rows_read"] / max(total, 1), 1)
            _progress(cur, import_id, "cleaning", pct, rows_read=stats["rows_read"])
            log(f"#{import_id} {stats['rows_read']:,} rows read")

        if not checked:
            raise ValueError("The file is empty")

        _check_cancel(import_id)
        _progress(cur, import_id, "saving", 92)
        enrich_sales(cur, stage_tbl)
        cur.execute(f"ANALYZE {stage_tbl}")
        skipped = stats["invalid_dates"]
        replaced = 0
        with conn.transaction():
            if mode == "replace_all":
                replaced = cur.execute("SELECT count(*) FROM sales").fetchone()[0]
                cur.execute("TRUNCATE sales")
            elif mode == "merge":
                # safest: add everything, skip lines that are already in the system.
                # Matching is tolerant, because the same sale often comes from different reports:
                # with/without invoice number, product code or name, with/without a time.
                skipped += cur.execute(f"DELETE FROM {stage_tbl} s WHERE {DUP_MATCH}").cur.rowcount
            elif mode == "append_new":
                last = cur.execute("SELECT max(invoice_date) FROM sales").fetchone()[0]
                if last is not None:
                    skipped += cur.execute(
                        f"SELECT count(*) FROM {stage_tbl} WHERE invoice_date <= ?", [last]
                    ).fetchone()[0]
                    cur.execute(f"DELETE FROM {stage_tbl} WHERE invoice_date <= ?", [last])
            elif mode == "replace_period":
                # replace rows of the same branches inside the file's date range (safe re-upload)
                cond = (f"day BETWEEN (SELECT min(day) FROM {stage_tbl}) AND "
                        f"(SELECT max(day) FROM {stage_tbl}) AND "
                        f"(branch IN (SELECT DISTINCT branch FROM {stage_tbl} WHERE branch IS NOT NULL)"
                        f" OR (branch IS NULL AND EXISTS "
                        f"(SELECT 1 FROM {stage_tbl} WHERE branch IS NULL)))")
                replaced = cur.execute(f"SELECT count(*) FROM sales WHERE {cond}").fetchone()[0]
                cur.execute(f"DELETE FROM sales WHERE {cond}")

            cur.execute(f"INSERT INTO sales SELECT * FROM {stage_tbl}")
            imported, dmin, dmax = cur.execute(
                f"SELECT count(*), min(day), max(day) FROM {stage_tbl}").fetchone()
            cur.execute(f"DROP TABLE {stage_tbl}")
            cur.execute(
                """UPDATE imports SET status='done', stage='finished', progress=100,
                   finished_at=now(), rows_read=?, rows_imported=?, rows_skipped=?,
                   rows_replaced=?, invalid_phones=?, invalid_dates=?, date_from=?, date_to=?
                   WHERE id=?""",
                [stats["rows_read"], imported, skipped, int(replaced), stats["invalid_phones"],
                 stats["invalid_dates"], dmin, dmax, import_id])
        cur.execute("ANALYZE sales")
        db.bump_version()
    except Exception as e:  # noqa: BLE001 - reported to the user
        if not isinstance(e, Cancelled):
            import traceback
            log(f"#{import_id} FAILED: {e}\n{traceback.format_exc()}")
        cur.execute(f"DROP TABLE IF EXISTS {stage_tbl}")
        cur.execute("UPDATE imports SET status='failed', message=?, finished_at=now() "
                    "WHERE id=?", [str(e)[:1000], import_id])
    finally:
        conn.close()
        if cleanup:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------- customer lists
DIRECTORY_COLS = ["phone", "phone_valid", "name", "first_name", "last_name", "address", "region",
                  "city", "district", "area", "email", "gender", "birth_date", "import_id"]


def enrich_sales(cur, table: str = "sales"):
    """Use the customer list to fill/correct names and districts of sales rows (by phone)."""
    cur.execute(f"""UPDATE {table} s SET district = d.district FROM customer_directory d
                    WHERE s.phone = d.phone AND d.district IS NOT NULL
                      AND s.district IS DISTINCT FROM d.district""")
    cur.execute(f"""UPDATE {table} s SET name = d.name FROM customer_directory d
                    WHERE s.phone = d.phone AND s.name IS NULL AND d.name IS NOT NULL""")


def build_customer_frame(raw: pd.DataFrame, mapping: dict) -> tuple[pd.DataFrame, dict]:
    def col(f):
        c = mapping.get(f)
        return _clean_text(raw[c]) if c and c in raw.columns else pd.Series(None, index=raw.index,
                                                                           dtype=object)

    stats = {"rows_read": len(raw), "invalid_phones": 0, "invalid_dates": 0}
    ph = raw[mapping["phone"]].astype(str)
    uniq = {v: normalize_egy_phone(v) for v in pd.unique(ph)}
    out = pd.DataFrame(index=raw.index)
    out["phone"] = ph.map(uniq).map(lambda v: v or None).astype(object)
    out["phone_valid"] = out["phone"].map(is_valid_egy_mobile)
    stats["invalid_phones"] = int((out["phone"].notna() & ~out["phone_valid"]).sum())

    first, last = col("first_name"), col("last_name")
    joined = (first.fillna("") + " " + last.fillna("")).str.strip().map(lambda v: v or None)
    out["first_name"], out["last_name"] = first, last
    out["name"] = col("name").fillna(joined)

    for f in ("region", "city", "district", "area", "email", "gender"):
        out[f] = col(f)
    parts = [col(f) for f in ("building", "street", "landmark", "area", "district", "city",
                              "region")]
    built = pd.concat(parts, axis=1).apply(
        lambda r: ", ".join(v for v in r if isinstance(v, str) and v), axis=1).map(lambda v: v or None) if len(raw) else None
    out["address"] = col("address").fillna(built) if len(raw) else None
    # district: from the file, else the area, else guessed from the address
    guessed = out["address"].map(lambda a: None if a is None else
                                 (lambda d: None if d == "Unknown" else d)(extract_district(a)))
    out["district"] = out["district"].fillna(out["area"]).fillna(guessed)

    bd = mapping.get("birth_date")
    out["birth_date"] = _parse_dates(raw[bd]).dt.date if bd and bd in raw.columns else None
    out = out[out["phone"].notna()]
    return out, stats


def run_customer_import(import_id: int, path: Path, mapping: dict, mode: str,
                        sheet: str | None = None, cleanup: bool = True):
    """Customer list: upsert one row per phone into customer_directory, then enrich sales."""
    conn = psycopg.connect(config.DATABASE_URL, autocommit=True)
    cur = db.Cursor(conn)
    stage_tbl = f"staging_c{import_id}"
    try:
        stats = {"rows_read": 0, "invalid_dates": 0, "invalid_phones": 0}
        cur.execute(f"DROP TABLE IF EXISTS {stage_tbl}")
        cur.execute(f"CREATE UNLOGGED TABLE {stage_tbl} (LIKE customer_directory INCLUDING DEFAULTS)")
        cur.execute(f"ALTER TABLE {stage_tbl} ADD COLUMN rn BIGSERIAL")
        _progress(cur, import_id, "reading", 1)
        checked = False
        for chunk, total in iter_chunks(path, sheet):
            if not checked:
                if not mapping.get("phone") or mapping["phone"] not in chunk.columns:
                    raise ValueError("Missing required column: phone")
                checked = True
            _check_cancel(import_id)
            frame, st = build_customer_frame(chunk, mapping)
            for k in stats:
                stats[k] += st[k]
            frame = frame.assign(import_id=import_id)[DIRECTORY_COLS]
            obj = frame.astype(object).where(frame.notna(), None)
            with cur.copy(f"COPY {stage_tbl} ({', '.join(DIRECTORY_COLS)}) FROM STDIN") as cp:
                for row in obj.itertuples(index=False, name=None):
                    cp.write_row(row)
            _progress(cur, import_id, "cleaning", 5 + 80 * min(stats["rows_read"] / max(total, 1), 1),
                      rows_read=stats["rows_read"])
        if not checked:
            raise ValueError("The file is empty")

        _progress(cur, import_id, "saving", 88)
        upd = ", ".join(f"{c} = coalesce(EXCLUDED.{c}, customer_directory.{c})"
                        for c in DIRECTORY_COLS if c not in ("phone", "import_id"))
        with conn.transaction():
            replaced = 0
            if mode == "replace_all":
                replaced = cur.execute("SELECT count(*) FROM customer_directory").fetchone()[0]
                cur.execute("TRUNCATE customer_directory")
            else:
                replaced = cur.execute(f"SELECT count(DISTINCT s.phone) FROM {stage_tbl} s "
                                       f"JOIN customer_directory d USING (phone)").fetchone()[0]
            cur.execute(f"""INSERT INTO customer_directory ({', '.join(DIRECTORY_COLS)})
                SELECT DISTINCT ON (phone) {', '.join(DIRECTORY_COLS)} FROM {stage_tbl}
                ORDER BY phone, rn DESC
                ON CONFLICT (phone) DO UPDATE SET {upd}, import_id = EXCLUDED.import_id,
                    updated_at = now()""")
            customers = cur.execute(f"SELECT count(DISTINCT phone) FROM {stage_tbl}").fetchone()[0]
            cur.execute(f"DROP TABLE {stage_tbl}")
            _progress(cur, import_id, "saving", 94)
            enrich_sales(cur)
            cur.execute(
                """UPDATE imports SET status='done', stage='finished', progress=100,
                   finished_at=now(), rows_read=?, rows_imported=?, rows_skipped=?,
                   rows_replaced=?, invalid_phones=?, invalid_dates=0 WHERE id=?""",
                [stats["rows_read"], customers, stats["rows_read"] - customers, int(replaced),
                 stats["invalid_phones"], import_id])
        cur.execute("ANALYZE customer_directory")
        db.bump_version()
    except Exception as e:  # noqa: BLE001 - reported to the user
        if not isinstance(e, Cancelled):
            import traceback
            log(f"#{import_id} FAILED: {e}\n{traceback.format_exc()}")
        cur.execute(f"DROP TABLE IF EXISTS {stage_tbl}")
        cur.execute("UPDATE imports SET status='failed', message=?, finished_at=now() "
                    "WHERE id=?", [str(e)[:1000], import_id])
    finally:
        conn.close()
        if cleanup:
            path.unlink(missing_ok=True)
