"""Automatic data feeds (SAP S/4HANA or any system), all using the same smart importer:

* push   - the system sends a file to POST /api/v1/files with an API key
* pull   - the platform downloads a report from a URL (file link or OData service) at set times
* inbox  - a file copied into the drop folder (DATA_DIR/inbox, e.g. by SFTP) is imported

Each file is analysed like a manual upload: every sheet is recognised (sales / customer list /
product list), columns are mapped (remembered mappings first), and lines already in the system are
skipped, so sending the same or an overlapping report again never duplicates data.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .. import config, db
from . import importer

INBOX = config.DATA_DIR / "inbox"
FEED_DIR = config.DATA_DIR / "feeds"
DEFAULT_MODES = {"sales": "merge", "customers": "upsert", "products": "upsert"}
REQUIRED = {"products": ["item_code"]}


def log(msg: str):
    print(f"[feeds] {datetime.now():%H:%M:%S} {msg}", flush=True)


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(db.get_settings().get("timezone") or "Africa/Cairo")
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


# ---------------------------------------------------------------- one file -> imports
def auto_import(path: Path, filename: str, source: str, wait: bool = False) -> list[dict]:
    """Analyse a file and import every recognised sheet. Returns [{import_id, sheet, kind, status}].
    Sheets that cannot be imported get a failed row in the import history with the reason."""
    from .columns import CUSTOMER_REQUIRED, REQUIRED_FIELDS
    req = {"sales": REQUIRED_FIELDS, "customers": CUSTOMER_REQUIRED, **REQUIRED}
    cur = db.cursor()
    out, jobs = [], []
    try:
        path = importer.unpack(path)
        digest = importer.file_sha256(path)
        same = db.one(cur, "SELECT id FROM imports WHERE file_hash = ? AND status = 'done' "
                           "ORDER BY id DESC LIMIT 1", [digest])
        pv = importer.preview(path)
    except Exception as e:  # noqa: BLE001 - unreadable file: one failed row
        iid = cur.execute("INSERT INTO imports (filename, kind, mode, status, stage, message, created_by, "
                          "finished_at) VALUES (?, 'sales', 'merge', 'failed', 'finished', ?, ?, now()) "
                          "RETURNING id", [filename, f"Could not read the file: {e}"[:1000], source]).fetchone()[0]
        Path(path).unlink(missing_ok=True)
        return [{"import_id": iid, "status": "failed", "message": str(e)}]
    if same:
        iid = cur.execute("INSERT INTO imports (filename, kind, mode, status, stage, message, created_by, "
                          "file_hash, finished_at) VALUES (?, 'sales', 'merge', 'done', 'finished', ?, ?, ?, now()) "
                          "RETURNING id", [filename, f"Same file as import #{same['id']} - nothing new",
                                           source, digest]).fetchone()[0]
        path.unlink(missing_ok=True)
        return [{"import_id": iid, "status": "skipped", "message": "same file already imported"}]
    sheets = [s for s in pv["sheets_info"] if s["kind"] in DEFAULT_MODES]
    for s in sheets:
        kind = s["kind"]
        mapping = {f: v for f, v in (s["mappings"].get(kind) or {}).items()}
        name = filename + (f" [{s['sheet']}]" if s.get("sheet") and len(sheets) > 1 else "")
        missing = [f for f in req[kind] if not mapping.get(f)]
        if missing:
            iid = cur.execute("INSERT INTO imports (filename, kind, mode, status, stage, message, created_by, "
                              "sheet, finished_at) VALUES (?, ?, ?, 'failed', 'finished', ?, ?, ?, now()) RETURNING id",
                              [name, kind, DEFAULT_MODES[kind],
                               "Columns not recognised: " + ", ".join(missing) +
                               ". Upload this report once by hand on Data upload and choose the columns - "
                               "the choice is remembered for the next automatic files.", source,
                               s.get("sheet")]).fetchone()[0]
            out.append({"import_id": iid, "sheet": s.get("sheet"), "kind": kind, "status": "failed"})
            continue
        iid = cur.execute(
            "INSERT INTO imports (filename, kind, mode, status, stage, mapping, created_by, sheet, file_hash, "
            "file_size) VALUES (?, ?, ?, 'running', 'queued', ?, ?, ?, ?, ?) RETURNING id",
            [name, kind, DEFAULT_MODES[kind], json.dumps(mapping), source, s.get("sheet"), digest,
             path.stat().st_size]).fetchone()[0]
        jobs.append({"import_id": iid, "kind": kind, "mode": DEFAULT_MODES[kind], "sheet": s.get("sheet"),
                     "mapping": {**mapping, "_date_order": s.get("date_order") or "dmy"}})
        out.append({"import_id": iid, "sheet": s.get("sheet"), "kind": kind, "status": "queued"})
    if not sheets:
        iid = cur.execute("INSERT INTO imports (filename, kind, mode, status, stage, message, created_by, "
                          "finished_at) VALUES (?, 'sales', 'merge', 'failed', 'finished', ?, ?, now()) RETURNING id",
                          [filename, "No sales, customer or product data recognised in this file", source]).fetchone()[0]
        out.append({"import_id": iid, "status": "failed"})
    if jobs:
        db.audit(source, "import_start", f"{filename}: " + ", ".join(f"#{j['import_id']} {j['kind']}" for j in jobs))
        if wait:
            importer.run_jobs(jobs, path)
        else:
            threading.Thread(target=importer.run_jobs, args=(jobs, path), daemon=True).start()
    else:
        path.unlink(missing_ok=True)
    return out


# ---------------------------------------------------------------- pull from a URL
def _odata_rows(data) -> tuple[list, str | None]:
    """OData v2 {"d": {"results": [...], "__next"}} or v4 {"value": [...], "@odata.nextLink"}."""
    if isinstance(data, list):
        return data, None
    if "d" in data:
        d = data["d"]
        return (d.get("results", d) if isinstance(d, dict) else d), (d.get("__next") if isinstance(d, dict) else None)
    return data.get("value", []), data.get("@odata.nextLink")


def _clean_odata(v):
    if isinstance(v, str):
        m = re.fullmatch(r"/Date\((-?\d+)(?:[+-]\d+)?\)/", v)  # OData v2 date
        if m:
            return datetime.fromtimestamp(int(m.group(1)) / 1000, ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")
        m = re.fullmatch(r"PT(\d+)H(\d+)M(\d+)S", v)  # Edm.Time
        if m:
            return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}:{int(m.group(3)):02d}"
    if isinstance(v, dict):
        return None
    return v


def download(feed: dict) -> tuple[Path, str]:
    """Fetch the feed URL to a local file (OData JSON is turned into a CSV)."""
    FEED_DIR.mkdir(parents=True, exist_ok=True)
    headers = {"Accept": "application/json, text/csv, application/octet-stream, */*"}
    auth = None
    if feed.get("auth_type") == "basic":
        auth = (feed.get("username") or "", feed.get("secret") or "")
    elif feed.get("auth_type") == "bearer":
        headers["Authorization"] = f"Bearer {feed.get('secret') or ''}"
    elif feed.get("auth_type") == "header" and feed.get("header_name"):
        headers[feed["header_name"]] = feed.get("secret") or ""
    url = feed["url"].replace("{today}", datetime.now(tz()).strftime("%Y-%m-%d")) \
        .replace("{yesterday}", (datetime.now(tz()) - timedelta(days=1)).strftime("%Y-%m-%d"))
    with httpx.Client(timeout=httpx.Timeout(600, connect=30), follow_redirects=True, auth=auth,
                      headers=headers, verify=not feed.get("insecure")) as c:
        r = c.get(url)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "json" in ctype or r.content[:1] in (b"{", b"["):
            rows, nxt = _odata_rows(r.json())
            pages = 0
            while nxt and pages < 500:  # server-side paging
                nxt = nxt if nxt.startswith("http") else httpx.URL(url).join(nxt)
                r = c.get(nxt)
                r.raise_for_status()
                more, nxt = _odata_rows(r.json())
                rows += more
                pages += 1
            path = FEED_DIR / f"{uuid.uuid4().hex}.csv"
            cols = []
            for row in rows:
                for k in row:
                    if k != "__metadata" and k not in cols:
                        cols.append(k)
            with path.open("w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                for row in rows:
                    w.writerow([_clean_odata(row.get(k)) for k in cols])
            return path, f"{feed['name']} {datetime.now(tz()):%Y-%m-%d %H%M}.csv"
        m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', r.headers.get("content-disposition", ""))
        name = m.group(1) if m else (Path(httpx.URL(url).path).name or f"{feed['name']}.xlsx")
        suffix = Path(name).suffix.lower()
        if suffix not in importer.EXCEL_SUFFIXES + (".csv", ".zip"):
            suffix = ".csv" if "csv" in ctype or "text" in ctype else ".xlsx"
        path = FEED_DIR / f"{uuid.uuid4().hex}{suffix}"
        path.write_bytes(r.content)
        return path, name


def run_feed(feed_id: int, by: str = "schedule") -> dict:
    cur = db.cursor()
    feed = db.one(cur, "SELECT * FROM data_feeds WHERE id = ?", [feed_id])
    if not feed:
        return {"ok": False, "message": "Feed not found"}
    cur.execute("UPDATE data_feeds SET last_run_at = now(), last_status = 'running', last_message = NULL "
                "WHERE id = ?", [feed_id])
    try:
        path, name = download(feed)
        res = auto_import(path, name, f"feed:{feed['name']}", wait=True)
        ok = all(r["status"] != "failed" for r in res)
        msg = ", ".join(f"#{r['import_id']} {r['status']}" for r in res)
        # the import result (rows added / skipped)
        ids = [r["import_id"] for r in res]
        rows = db.rows(cur, "SELECT id, status, rows_imported, rows_skipped, message FROM imports "
                            "WHERE id = ANY(?)", [ids]) if ids else []
        if rows:
            ok = all(x["status"] == "done" for x in rows)
            msg = "; ".join(f"#{x['id']} {x['status']}: +{x['rows_imported'] or 0} new, "
                            f"{x['rows_skipped'] or 0} skipped" + (f" ({x['message']})" if x["message"] and
                                                                    x["status"] != "done" else "") for x in rows)
    except Exception as e:  # noqa: BLE001 - shown in Settings
        ok, msg = False, f"{type(e).__name__}: {e}"[:1000]
    cur.execute("UPDATE data_feeds SET last_status = ?, last_message = ? WHERE id = ?",
                ["ok" if ok else "failed", msg, feed_id])
    log(f"feed {feed['name']} ({by}): {'ok' if ok else 'FAILED'} {msg}")
    return {"ok": ok, "message": msg}


def due_feeds(now: datetime) -> list[int]:
    """Feeds whose time of day has passed today and that have not run since that time."""
    out = []
    for f in db.rows(db.cursor(), "SELECT id, times, last_run_at FROM data_feeds WHERE enabled"):
        last = f["last_run_at"]
        for t in re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", f["times"] or ""):
            at = now.replace(hour=int(t[0]), minute=int(t[1]), second=0, microsecond=0)
            # last_run_at is stored in server time (UTC in Docker); compare in the same zone
            last_local = last.replace(tzinfo=ZoneInfo("UTC")).astimezone(now.tzinfo) if last else None
            if at <= now < at + timedelta(hours=6) and (last_local is None or last_local < at):
                out.append(f["id"])
                break
    return out


# ---------------------------------------------------------------- inbox folder
def scan_inbox():
    INBOX.mkdir(parents=True, exist_ok=True)
    done, failed = INBOX / "done", INBOX / "failed"
    done.mkdir(exist_ok=True)
    failed.mkdir(exist_ok=True)
    for p in sorted(INBOX.iterdir()):
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() not in importer.EXCEL_SUFFIXES + (".csv", ".zip"):
            continue
        try:
            st = p.stat()
            if time.time() - st.st_mtime < 20:  # still being copied
                continue
            work = FEED_DIR / f"{uuid.uuid4().hex}{p.suffix.lower()}"
            FEED_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, work)
            res = auto_import(work, p.name, "inbox", wait=True)
            target = (failed if any(r["status"] == "failed" for r in res) else done) / \
                f"{datetime.now():%Y%m%d-%H%M%S}_{p.name}"
            shutil.move(str(p), target)
            log(f"inbox {p.name}: {res}")
        except Exception as e:  # noqa: BLE001
            log(f"inbox {p.name} failed: {e}")
            try:
                shutil.move(str(p), failed / f"{datetime.now():%Y%m%d-%H%M%S}_{p.name}")
            except Exception:  # noqa: BLE001
                pass
    # keep 30 days of processed files
    for d in (done, failed):
        for p in d.iterdir():
            if time.time() - p.stat().st_mtime > 30 * 86400:
                p.unlink(missing_ok=True)


# ---------------------------------------------------------------- scheduler
_started = False


def start_scheduler():
    global _started
    if _started:
        return
    _started = True

    def loop():
        time.sleep(30)
        while True:
            try:
                scan_inbox()
                for fid in due_feeds(datetime.now(tz())):
                    run_feed(fid)
            except Exception as e:  # noqa: BLE001
                log(f"scheduler: {e}")
            time.sleep(60)

    threading.Thread(target=loop, daemon=True, name="feeds").start()
