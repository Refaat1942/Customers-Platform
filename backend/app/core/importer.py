"""Excel/CSV import: read -> map columns -> clean -> store in `sales`."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .. import db
from .address import extract_district
from .columns import FIELDS, REQUIRED_FIELDS, clean_col_name, find_columns
from .phone import is_valid_egy_mobile, normalize_egy_phone

SEASONS = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
           6: "Summer", 7: "Summer", 8: "Summer", 9: "Autumn", 10: "Autumn", 11: "Autumn"}

IMPORT_MODES = ("replace_period", "append_new", "replace_all")

TEXT_FIELDS = ["name", "branch", "address", "district", "invoice_no", "invoice_type",
               "item_code", "item_name", "material_group", "item_category", "item_unit"]


# ---------------------------------------------------------------- reading
def read_file(path: Path, nrows=None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            df = pd.read_csv(path, nrows=nrows, dtype=object, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(path, nrows=nrows, dtype=object, encoding="cp1256")
    elif suffix == ".xls":
        df = pd.read_excel(path, nrows=nrows, engine="xlrd")
    else:
        df = pd.read_excel(path, nrows=nrows, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, [c for c in df.columns if not c.startswith("Unnamed:")] or df.columns]
    return df


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


def preview(path: Path) -> dict:
    df = read_file(path, nrows=20)
    cols = list(df.columns)
    return {
        "columns": cols,
        "mapping": suggest_mapping(cols),
        "sample": [{c: _jsonable(v) for c, v in r.items()} for r in df.to_dict("records")],
    }


# ---------------------------------------------------------------- cleaning
def _parse_dates(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        return pd.to_datetime(s, errors="coerce")
    num = pd.to_numeric(s, errors="coerce")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    serial = num.between(20000, 80000)  # Excel serial day numbers
    if serial.any():
        out[serial] = pd.to_datetime(num[serial], unit="D", origin="1899-12-30")
    rest = ~serial & s.notna()
    if rest.any():
        out[rest] = pd.to_datetime(s[rest].astype(str).str.strip(), errors="coerce",
                                   dayfirst=True, format="mixed")
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
def run_import(import_id: int, path: Path, mapping: dict, mode: str):
    cur = db.cursor()
    try:
        raw = read_file(path)
        missing = [f for f in REQUIRED_FIELDS if not mapping.get(f) or mapping[f] not in raw.columns]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")

        frame, stats = build_frame(raw, mapping)
        skipped = stats["invalid_dates"]
        replaced = 0

        cur.execute("BEGIN TRANSACTION")
        if mode == "replace_all":
            replaced = cur.execute("SELECT count(*) FROM sales").fetchone()[0]
            cur.execute("DELETE FROM sales")
        elif mode == "append_new":
            last = cur.execute("SELECT max(invoice_date) FROM sales").fetchone()[0]
            if last is not None:
                keep = frame["invoice_date"] > pd.Timestamp(last)
                skipped += int((~keep).sum())
                frame = frame[keep]
        elif mode == "replace_period" and len(frame):
            # delete existing rows of the same branches inside the file's date range
            dmin, dmax = frame["day"].min(), frame["day"].max()
            branches = [b for b in frame["branch"].dropna().unique().tolist()]
            has_null = bool(frame["branch"].isna().any())
            cond = "day BETWEEN ? AND ? AND (branch IN (SELECT unnest(?::VARCHAR[]))"
            cond += " OR branch IS NULL)" if has_null else ")"
            params = [dmin.date(), dmax.date(), branches]
            replaced = cur.execute(f"SELECT count(*) FROM sales WHERE {cond}", params).fetchone()[0]
            cur.execute(f"DELETE FROM sales WHERE {cond}", params)

        frame = frame.assign(import_id=import_id)
        cols = ["import_id", "phone", "phone_valid", "name", "branch", "address", "district",
                "invoice_no", "visit_key", "invoice_date", "day", "season", "invoice_type",
                "item_code", "item_name", "material_group", "item_category", "quantity",
                "item_unit", "item_price"]
        frame = frame[cols]
        cur.register("_import_frame", frame)
        cur.execute(f"INSERT INTO sales ({', '.join(cols)}) SELECT {', '.join(cols)} FROM _import_frame")
        cur.unregister("_import_frame")

        cur.execute(
            """UPDATE imports SET status='done', finished_at=current_timestamp,
               rows_read=?, rows_imported=?, rows_skipped=?, rows_replaced=?,
               invalid_phones=?, invalid_dates=?, date_from=?, date_to=? WHERE id=?""",
            [stats["rows_read"], len(frame), skipped, int(replaced), stats["invalid_phones"],
             stats["invalid_dates"],
             frame["day"].min().date() if len(frame) else None,
             frame["day"].max().date() if len(frame) else None, import_id],
        )
        cur.execute("COMMIT")
    except Exception as e:  # noqa: BLE001 - reported to the user
        try:
            cur.execute("ROLLBACK")
        except Exception:  # noqa: BLE001
            pass
        cur.execute("UPDATE imports SET status='failed', message=?, finished_at=current_timestamp "
                    "WHERE id=?", [str(e)[:1000], import_id])
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
