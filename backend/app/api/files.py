"""File push API for SAP S/4HANA (or any system): send a report file, it is imported automatically.

    POST /api/v1/files            header X-API-Key: cpk_...
         body = the file itself (Content-Type: application/octet-stream, ?filename=Daily Sales.xlsx)
         or multipart/form-data with a field named "file"
    GET  /api/v1/files/{import_id} status of one import
"""

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import config, db
from ..core import feeds, importer
from .pos import pos_client

router = APIRouter(prefix="/api/v1/files", tags=["File push (SAP)"])
ALLOWED = importer.EXCEL_SUFFIXES + (".csv", ".zip")


@router.post("", status_code=202)
async def push_file(request: Request, filename: str | None = Query(default=None, max_length=200),
                    client: dict = Depends(pos_client)):
    """Accepts the file and imports it in the background. Returns the import ids to follow."""
    feeds.FEED_DIR.mkdir(parents=True, exist_ok=True)
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    ctype = request.headers.get("content-type", "")
    tmp = feeds.FEED_DIR / f"push_{uuid.uuid4().hex}"
    size = 0
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        up = form.get("file")
        if up is None or not hasattr(up, "filename"):
            raise HTTPException(400, "Send the file in a form field named 'file'")
        filename = filename or up.filename
        with tmp.open("wb") as fh:
            shutil.copyfileobj(up.file, fh, 1024 * 1024)
        size = tmp.stat().st_size
    else:
        with tmp.open("wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    fh.close()
                    tmp.unlink(missing_ok=True)
                    raise HTTPException(413, f"File larger than {config.MAX_UPLOAD_MB} MB")
                fh.write(chunk)
    filename = (filename or "").strip() or "SAP report.xlsx"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, f"File type must be one of {', '.join(ALLOWED)} (set ?filename=...)")
    if size == 0:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, "The file is empty")
    path = tmp.rename(tmp.with_suffix(suffix))
    res = feeds.auto_import(path, filename, f"api:{client['name']}")
    return {"accepted": True, "filename": filename, "size": size, "imports": res,
            "status_url": "/api/v1/files/{import_id}"}


@router.get("/{import_id}")
def file_status(import_id: int, client: dict = Depends(pos_client)):
    row = db.one(db.cursor(), """SELECT id, filename, kind, status, stage, progress, message, rows_read,
        rows_imported, rows_skipped, rows_replaced, invalid_phones, invalid_dates, date_from, date_to,
        created_at, finished_at FROM imports WHERE id = ? AND created_by = ?""",
                 [import_id, f"api:{client['name']}"])
    if not row:
        raise HTTPException(404, "No import with this id was sent with this key")
    return row
