import json
import shutil
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
import pandas as pd
from pydantic import BaseModel, Field

from .. import config, db
from ..auth import admin_user, check_password, current_user, hash_password, make_token, public_user
from ..core import analytics as an
from ..core import export as ex
from ..core import importer
from ..core.columns import FIELDS, REQUIRED_FIELDS

router = APIRouter(prefix="/api")

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ====================================================================== helpers
def filters(
    user: dict = Depends(current_user),
    date_from: date | None = None,
    date_to: date | None = None,
    branch: list[str] = Query(default=[]),
    type: list[str] = Query(default=[]),  # noqa: A002
    district: list[str] = Query(default=[]),
    season: list[str] = Query(default=[]),
) -> an.Filters:
    return an.Filters(date_from=date_from, date_to=date_to, branches=branch, types=type,
                      districts=district, seasons=season,
                      allowed_branches=user["branches"] or None)


def xlsx_response(content: bytes, filename: str) -> Response:
    return Response(content, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def filter_meta(f: an.Filters, lang: str) -> list[tuple[str, str]]:
    ar = lang == "ar"
    return [
        ("من" if ar else "From", ex.fmt_value(f.date_from)),
        ("إلى" if ar else "To", ex.fmt_value(f.date_to)),
        ("الفروع" if ar else "Branches", ", ".join(f.branches) or ("الكل" if ar else "All")),
        ("نوع البيع" if ar else "Sales types", ", ".join(f.types) or ("الكل" if ar else "All")),
        ("المنطقة" if ar else "Districts", ", ".join(f.districts) or ("الكل" if ar else "All")),
        ("الموسم" if ar else "Seasons", ", ".join(f.seasons) or ("الكل" if ar else "All")),
    ]


# ====================================================================== auth
class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn):
    u = db.one(db.cursor(), "SELECT * FROM users WHERE lower(username) = lower(?)",
               [body.username.strip()])
    if not u or not u["active"] or not check_password(body.password, u["password_hash"]):
        raise HTTPException(401, "Wrong username or password")
    return {"token": make_token(u["id"]), "user": public_user(u)}


@router.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return user


class ProfileIn(BaseModel):
    language: Literal["en", "ar"] | None = None
    full_name: str | None = None
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8)


@router.put("/auth/me")
def update_me(body: ProfileIn, user: dict = Depends(current_user)):
    cur = db.cursor()
    if body.language:
        cur.execute("UPDATE users SET language = ? WHERE id = ?", [body.language, user["id"]])
    if body.full_name is not None:
        cur.execute("UPDATE users SET full_name = ? WHERE id = ?", [body.full_name, user["id"]])
    if body.new_password:
        row = db.one(cur, "SELECT password_hash FROM users WHERE id = ?", [user["id"]])
        if not check_password(body.current_password or "", row["password_hash"]):
            raise HTTPException(400, "Current password is wrong")
        cur.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                    [hash_password(body.new_password), user["id"]])
    return public_user(db.one(cur, "SELECT * FROM users WHERE id = ?", [user["id"]]))


# ====================================================================== meta & settings
@router.get("/meta")
def get_meta(user: dict = Depends(current_user)):
    m = an.meta(user["branches"] or None)
    last = db.one(db.cursor(), "SELECT id, filename, finished_at FROM imports WHERE status='done' "
                               "ORDER BY id DESC LIMIT 1")
    return {**m, "last_import": last, "settings": db.get_settings()}


class SettingsIn(BaseModel):
    active_days: int = Field(ge=1)
    attention_days: int = Field(ge=1)
    high_value_spend: float = Field(ge=0)
    loyalty_spend: float = Field(ge=0)
    loyalty_visits: int = Field(ge=1)


@router.get("/settings")
def get_settings(user: dict = Depends(current_user)):
    return db.get_settings()


@router.put("/settings")
def put_settings(body: SettingsIn, user: dict = Depends(admin_user)):
    if body.attention_days <= body.active_days:
        raise HTTPException(400, "'Needs attention' days must be greater than 'Active' days")
    db.save_settings(body.model_dump())
    return db.get_settings()


# ====================================================================== summary
@router.get("/summary")
def get_summary(f: an.Filters = Depends(filters), export: bool = False, lang: str = "en"):
    res = an.summary(f, db.get_settings())
    if not export:
        return res
    ar = lang == "ar"
    k, s, ins = res["kpis"], res["segments"], res["insights"]
    kpi_rows = [
        ("العملاء" if ar else "Customers", k["customers"]),
        ("الفواتير" if ar else "Invoices", k["invoices"]),
        ("إجمالي المبيعات" if ar else "Total sales", k["total_sales"]),
        ("متوسط لكل عميل" if ar else "Avg spend / customer", k["avg_per_customer"]),
        ("متوسط الفاتورة" if ar else "Avg invoice", k["avg_invoice"]),
        ("عملاء جدد" if ar else "New customers", res["new_customers"]),
        ("نشط" if ar else "Active", s["active"]),
        ("يحتاج متابعة" if ar else "Needs attention", s["attention"]),
        ("غير نشط" if ar else "Inactive", s["inactive"]),
        ("قيمة عالية" if ar else "High value", s["high_value"]),
        ("عملاء أوفياء" if ar else "Loyal", s["loyal"]),
    ] + [(ex.label(key, lang), ex.VALUES.get(v, (v, v))[1 if ar else 0] if v else "-")
         for key, v in ins.items()]
    kpi_df = pd.DataFrame(kpi_rows, columns=[ex.label("metric", lang), ex.label("value", lang)])
    sheets = [
        ("الملخص" if ar else "Summary", kpi_df),
        ("شهري" if ar else "Monthly", ex.frame(res["monthly"], ["month", "sales", "customers", "invoices"], lang)),
        ("الفروع" if ar else "Branches", ex.frame(res["by_branch"], ["branch", "sales", "customers", "invoices", "avg_per_customer"], lang)),
        ("نوع البيع" if ar else "Sales types", ex.frame(res["by_type"], ["sales_type", "sales", "invoices"], lang)),
        ("المواسم" if ar else "Seasons", ex.frame(res["by_season"], ["season", "sales", "invoices"], lang)),
        ("أفضل الأصناف" if ar else "Top items", ex.frame(res["top_items"], ["item", "sales", "quantity", "customers"], lang)),
    ]
    title = "تقرير الملخص العام" if ar else "Overall Summary Report"
    return xlsx_response(ex.workbook(sheets, lang, title, filter_meta(f, lang)), "summary_report.xlsx")


# ====================================================================== customers
CUSTOMER_VIEWS = {
    "customers": ["phone", "name", "branch", "district", "total_spent", "visits", "first_visit",
                  "last_visit", "days_since", "avg_per_visit", "avg_days_between",
                  "top_sales_type", "status"],
    "business": ["phone", "name", "branch", "total_spent", "visits", "top_material",
                 "top_category", "top_sales_type", "top_season", "loyal"],
    "recommendations": ["phone", "name", "branch", "total_spent", "visits", "last_visit",
                        "days_since", "avg_per_visit", "status", "high_value", "action"],
}


@router.get("/customers")
def get_customers(
    f: an.Filters = Depends(filters),
    q: str | None = None,
    status: list[str] = Query(default=[]),
    flag: Literal["high_value", "loyal", "invalid_phone"] | None = None,
    sort: str = "priority",
    desc: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    export: bool = False,
    view: Literal["customers", "business", "recommendations"] = "customers",
    lang: str = "en",
):
    res = an.list_customers(f, db.get_settings(), q=q, status=status or None, flag=flag,
                            sort=sort, desc=desc, page=page, page_size=page_size,
                            limit_all=export)
    for r in res["rows"]:
        r["action"] = ex.ACTIONS.get(r["status"])
    if not export:
        return res
    cols = CUSTOMER_VIEWS[view]
    names = {"customers": ("Customers", "العملاء"), "business": ("Business", "تحليل الأعمال"),
             "recommendations": ("Recommendations", "التوصيات")}[view]
    sheet = names[1] if lang == "ar" else names[0]
    content = ex.workbook([(sheet, ex.frame(res["rows"], cols, lang))], lang, sheet,
                          filter_meta(f, lang))
    return xlsx_response(content, f"{view}_{date.today().isoformat()}.xlsx")


@router.get("/customers/{phone}")
def get_customer(phone: str, f: an.Filters = Depends(filters), export: bool = False,
                 lang: str = "en"):
    res = an.customer_profile(phone, f, db.get_settings())
    if not res:
        raise HTTPException(404, "Customer not found")
    res["summary"]["action"] = ex.ACTIONS.get(res["summary"]["status"])
    if not export:
        return res
    s = res["summary"]
    info_cols = CUSTOMER_VIEWS["customers"] + ["top_material", "top_category", "top_season",
                                                "loyal", "high_value", "action"]
    info = ex.frame([s], info_cols, lang).T.reset_index()
    info.columns = [ex.label("metric", lang), ex.label("value", lang)]
    sheets = [
        ("العميل" if lang == "ar" else "Customer", info),
        ("الزيارات" if lang == "ar" else "Visits",
         ex.frame(res["visits"], ["date", "branch", "sales_type", "lines", "total", "items"], lang)),
        ("الأصناف" if lang == "ar" else "Items",
         ex.frame(res["top_items"], ["item", "quantity", "sales", "times"], lang)),
        ("شهري" if lang == "ar" else "Monthly",
         ex.frame(res["monthly"], ["month", "sales", "visits"], lang)),
    ]
    return xlsx_response(ex.workbook(sheets, lang), f"customer_{phone}.xlsx")


# ====================================================================== area
@router.get("/area")
def get_area(f: an.Filters = Depends(filters), min_customers: int = Query(5, ge=1),
             export: bool = False, lang: str = "en"):
    res = an.area(f, min_customers)
    if not export:
        return res
    ar = lang == "ar"
    cols = ["district", "sales", "customers", "invoices", "spend_per_customer", "share"]
    sheets = [
        ("المناطق" if ar else "Districts", ex.frame(res["districts"], cols, lang)),
        ("الفرع والمنطقة" if ar else "Branch x District",
         ex.frame(res["branch_district"], ["branch", "district", "rank", "sales", "customers",
                                           "spend_per_customer"], lang)),
        ("مناطق ضعيفة" if ar else "Weak districts", ex.frame(res["weak"], cols, lang)),
    ]
    title = "تقرير المناطق" if ar else "Area Report"
    return xlsx_response(ex.workbook(sheets, lang, title, filter_meta(f, lang)), "area_report.xlsx")


# ====================================================================== raw sales
@router.get("/sales")
def get_sales(f: an.Filters = Depends(filters), q: str | None = None,
              sort: str = "invoice_date", desc: bool = True,
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
              export: bool = False, lang: str = "en"):
    res = an.list_sales(f, q=q, sort=sort, desc=desc, page=page, page_size=page_size,
                        limit_all=export)
    if not export:
        return res
    sheet = "المبيعات" if lang == "ar" else "Transactions"
    return xlsx_response(ex.workbook([(sheet, ex.frame(res["rows"], an.SALES_COLUMNS, lang))],
                                     lang, sheet, filter_meta(f, lang)),
                         f"transactions_{date.today().isoformat()}.xlsx")


# ====================================================================== imports
_pending: dict[str, dict] = {}


@router.post("/imports/upload")
def upload(file: UploadFile = File(...), user: dict = Depends(admin_user)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".xlsx", ".xls", ".csv", ".xlsm"):
        raise HTTPException(400, "Please upload an Excel (.xlsx / .xls) or CSV file")
    token = uuid.uuid4().hex
    path = config.UPLOAD_DIR / f"{token}{suffix}"
    with path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    if path.stat().st_size > config.MAX_UPLOAD_MB * 1024 * 1024:
        path.unlink()
        raise HTTPException(400, f"File is larger than {config.MAX_UPLOAD_MB} MB")
    try:
        pv = importer.preview(path)
    except Exception as e:  # noqa: BLE001
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not read the file: {e}") from e
    _pending[token] = {"path": path, "filename": file.filename, "columns": pv["columns"]}
    return {"upload_id": token, "filename": file.filename, **pv,
            "fields": FIELDS, "required": REQUIRED_FIELDS, "modes": list(importer.IMPORT_MODES)}


class CommitIn(BaseModel):
    upload_id: str
    mapping: dict[str, str | None]
    mode: Literal["replace_period", "append_new", "replace_all"] = "replace_period"
    remember_mapping: bool = True


@router.post("/imports/commit")
def commit(body: CommitIn, user: dict = Depends(admin_user)):
    p = _pending.pop(body.upload_id, None)
    if not p or not p["path"].exists():
        raise HTTPException(404, "Upload expired, please upload the file again")
    mapping = {f: (body.mapping.get(f) or None) for f in FIELDS}
    missing = [f for f in REQUIRED_FIELDS if not mapping[f]]
    if missing:
        _pending[body.upload_id] = p
        raise HTTPException(400, f"Please choose a column for: {', '.join(missing)}")
    cur = db.cursor()
    if body.remember_mapping:
        cur.execute("INSERT OR REPLACE INTO saved_mappings VALUES (?, ?)",
                    [importer.header_signature(p["columns"]), json.dumps(mapping)])
    imp_id = cur.execute(
        "INSERT INTO imports (filename, mode, status, mapping, created_by) "
        "VALUES (?, ?, 'running', ?, ?) RETURNING id",
        [p["filename"], body.mode, json.dumps(mapping), user["username"]]).fetchone()[0]
    threading.Thread(target=importer.run_import, args=(imp_id, p["path"], mapping, body.mode),
                     daemon=True).start()
    return {"import_id": imp_id}


@router.get("/imports")
def list_imports(user: dict = Depends(admin_user)):
    return db.rows(db.cursor(), "SELECT * EXCLUDE (mapping) FROM imports ORDER BY id DESC LIMIT 100")


@router.get("/imports/{imp_id}")
def get_import(imp_id: int, user: dict = Depends(admin_user)):
    r = db.one(db.cursor(), "SELECT * FROM imports WHERE id = ?", [imp_id])
    if not r:
        raise HTTPException(404, "Import not found")
    return r


@router.delete("/imports/{imp_id}")
def delete_import(imp_id: int, user: dict = Depends(admin_user)):
    cur = db.cursor()
    n = cur.execute("SELECT count(*) FROM sales WHERE import_id = ?", [imp_id]).fetchone()[0]
    cur.execute("DELETE FROM sales WHERE import_id = ?", [imp_id])
    cur.execute("UPDATE imports SET status='deleted', message=? WHERE id = ?",
                [f"{n} rows removed", imp_id])
    return {"deleted_rows": n}


# ====================================================================== users
class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str | None = None
    role: Literal["admin", "manager"] = "manager"
    branches: list[str] = []
    language: Literal["en", "ar"] = "en"
    active: bool = True
    password: str | None = Field(default=None, min_length=8)


@router.get("/users")
def list_users(user: dict = Depends(admin_user)):
    return [public_user(u) for u in db.rows(db.cursor(), "SELECT * FROM users ORDER BY id")]


@router.post("/users")
def create_user(body: UserIn, user: dict = Depends(admin_user)):
    if not body.password:
        raise HTTPException(400, "Password is required (8+ characters)")
    cur = db.cursor()
    if db.one(cur, "SELECT id FROM users WHERE lower(username) = lower(?)", [body.username]):
        raise HTTPException(400, "Username already exists")
    cur.execute(
        "INSERT INTO users (username, password_hash, full_name, role, branches, language, active) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [body.username.strip(), hash_password(body.password), body.full_name, body.role,
         json.dumps(body.branches), body.language, body.active])
    return {"ok": True}


@router.put("/users/{uid}")
def update_user(uid: int, body: UserIn, user: dict = Depends(admin_user)):
    cur = db.cursor()
    if not db.one(cur, "SELECT id FROM users WHERE id = ?", [uid]):
        raise HTTPException(404, "User not found")
    if uid == user["id"] and (body.role != "admin" or not body.active):
        raise HTTPException(400, "You cannot remove your own admin access")
    cur.execute(
        "UPDATE users SET username=?, full_name=?, role=?, branches=?, language=?, active=? "
        "WHERE id=?",
        [body.username.strip(), body.full_name, body.role, json.dumps(body.branches),
         body.language, body.active, uid])
    if body.password:
        cur.execute("UPDATE users SET password_hash=? WHERE id=?",
                    [hash_password(body.password), uid])
    return {"ok": True}


@router.delete("/users/{uid}")
def delete_user(uid: int, user: dict = Depends(admin_user)):
    if uid == user["id"]:
        raise HTTPException(400, "You cannot delete yourself")
    db.cursor().execute("DELETE FROM users WHERE id = ?", [uid])
    return {"ok": True}
