"""Excel/CSV import: read -> map columns -> clean -> store in `sales`."""

import hashlib
import json
import shutil
import zipfile
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from python_calamine import CalamineWorkbook

import psycopg

from .. import config, db
from .address import extract_district
from .columns import FIELDS, REQUIRED_FIELDS, clean_col_name, find_columns
from .phone import is_valid_egy_mobile, normalize_egy_phone

SEASONS = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
           6: "Summer", 7: "Summer", 8: "Summer", 9: "Autumn", 10: "Autumn", 11: "Autumn"}

IMPORT_MODES = ("replace_period", "append_new", "replace_all")

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


def header_signature(columns) -> str:
    key = "|".join(sorted(clean_col_name(c) for c in columns))
    return hashlib.sha1(key.encode()).hexdigest()


def suggest_mapping(columns) -> dict:
    """Saved mapping for this header layout if any, else the automatic guess."""
    cur = db.cursor()
    saved = db.one(cur, "SELECT mapping FROM saved_mappings WHERE signature = ?",
                   [header_signature(columns)])
    if saved:
        m = json.loads(saved["mapping"])
        return {f: (m.get(f) if m.get(f) in columns else None) for f in FIELDS}
    return find_columns(columns)


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


def preview(path: Path, sheet: str | None = None) -> dict:
    sheets = sheet_names(path)
    sheet = sheet or (sheets[0] if sheets else None)
    df = read_file(path, nrows=20, sheet=sheet)
    cols = list(df.columns)
    return {
        "sheets": sheets,
        "sheet": sheet,
        "columns": cols,
        "mapping": suggest_mapping(cols),
        "sample": [{c: _jsonable(v) for c, v in r.items()} for r in df.to_dict("records")],
    }


# ---------------------------------------------------------------- cleaning
def _parse_dates(s: pd.Series) -> pd.Series:
    """Excel datetimes, Excel serial numbers, ISO text (yyyy-mm-dd) and Egyptian dd/mm/yyyy text."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return pd.to_datetime(s, errors="coerce")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")

    is_dt = s.map(lambda v: isinstance(v, (datetime, date)))
    if is_dt.any():
        out[is_dt] = pd.to_datetime(s[is_dt], errors="coerce")

    rest = ~is_dt & s.notna()
    num = pd.to_numeric(s[rest], errors="coerce")
    serial = num.between(20000, 80000)  # Excel serial day numbers
    if serial.any():
        idx = num[serial].index
        out[idx] = pd.to_datetime(num[serial], unit="D", origin="1899-12-30")
        rest[idx] = False

    if rest.any():
        txt = s[rest].astype(str).str.strip()
        iso = txt.str.match(r"^\d{4}-\d{1,2}-\d{1,2}")
        if iso.any():
            out[txt[iso].index] = pd.to_datetime(txt[iso], errors="coerce", format="ISO8601")
        if (~iso).any():
            out[txt[~iso].index] = pd.to_datetime(txt[~iso], errors="coerce", dayfirst=True,
                                                  format="mixed")
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
    out["phone"] = ph.astype(str).map(uniq).replace("", None)
    out["phone_valid"] = out["phone"].map(lambda p: bool(p) and is_valid_egy_mobile(p))
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


def _warm_cache():
    """Pre-compute the default dashboard so the first page view after an import is instant."""
    from . import analytics as an
    try:
        f, s = an.Filters(), db.get_settings()
        db.cached(("summary", f.key()), lambda: an.summary(f, s))
        db.cached(("insights", f.key()), lambda: an.insights(f, s))
    except Exception:  # noqa: BLE001 - only an optimisation
        pass


def run_import(import_id: int, path: Path, mapping: dict, mode: str, sheet: str | None = None):
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
            frame, st = build_frame(chunk, mapping)
            for k in stats:
                stats[k] += st[k]
            _copy_frame(cur, stage_tbl, frame.assign(import_id=import_id)[SALES_COLS])
            pct = 5 + 85 * min(stats["rows_read"] / max(total, 1), 1)
            _progress(cur, import_id, "cleaning", pct, rows_read=stats["rows_read"])

        if not checked:
            raise ValueError("The file is empty")

        _progress(cur, import_id, "saving", 92)
        cur.execute(f"ANALYZE {stage_tbl}")
        skipped = stats["invalid_dates"]
        replaced = 0
        with conn.transaction():
            if mode == "replace_all":
                replaced = cur.execute("SELECT count(*) FROM sales").fetchone()[0]
                cur.execute("TRUNCATE sales")
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
        _warm_cache()
    except Exception as e:  # noqa: BLE001 - reported to the user
        cur.execute(f"DROP TABLE IF EXISTS {stage_tbl}")
        cur.execute("UPDATE imports SET status='failed', message=?, finished_at=now() "
                    "WHERE id=?", [str(e)[:1000], import_id])
    finally:
        conn.close()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
