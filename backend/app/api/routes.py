import json
import shutil
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .. import config, db
from ..auth import (check_password, client_ip, current_user, hash_password, login_allowed,
                    login_failed, make_token, public_user, require, role_permissions)
from ..core import ai
from ..core import analytics as an
from ..core import export as ex
from ..core import importer
from ..core.columns import CUSTOMER_FIELDS, CUSTOMER_REQUIRED, FIELDS, REQUIRED_FIELDS
from ..permissions import ALL as ALL_PERMISSIONS
from ..permissions import PERMISSIONS

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


def audit(user: dict | None, action: str, details: str = ""):
    db.audit(user["username"] if user else None, action, details,
             user.get("ip") if user else None)


def mask_phone(p: str | None) -> str | None:
    if not p:
        return p
    return p[:3] + "****" + p[-4:] if len(p) > 7 else "****"


def protect(rows: list[dict], user: dict) -> list[dict]:
    """Hide phone numbers from users without the 'phones' permission."""
    if "phones" in user["permissions"]:
        return rows
    for r in rows:
        if "phone" in r:
            r["phone"] = mask_phone(r["phone"])
    return rows


def need_export(user: dict):
    if "export" not in user["permissions"]:
        raise HTTPException(403, "You don't have permission to download reports")


def xlsx_response(content: bytes, filename: str) -> Response:
    return Response(content, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def filter_text(f: an.Filters) -> str:
    parts = [f"{f.date_from or '...'} -> {f.date_to or '...'}"]
    for k, v in (("branch", f.branches), ("type", f.types), ("district", f.districts),
                 ("season", f.seasons)):
        if v:
            parts.append(f"{k}={','.join(v)}")
    return " ".join(parts)


def filter_meta(f: an.Filters, lang: str) -> list[tuple[str, str]]:
    ar = lang == "ar"
    all_ = "الكل" if ar else "All"
    return [
        ("من" if ar else "From", ex.fmt_value(f.date_from)),
        ("إلى" if ar else "To", ex.fmt_value(f.date_to)),
        ("الفروع" if ar else "Branches", ", ".join(f.branches or f.allowed_branches or []) or all_),
        ("نوع البيع" if ar else "Sales types", ", ".join(f.types) or all_),
        ("المنطقة" if ar else "Districts", ", ".join(f.districts) or all_),
        ("الموسم" if ar else "Seasons", ", ".join(f.seasons) or all_),
        ("تاريخ التقرير" if ar else "Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]


# ====================================================================== auth
class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, request: Request):
    ip = client_ip(request)
    key = f"{ip}|{body.username.lower()}"
    if not login_allowed(key):
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    u = db.one(db.cursor(), "SELECT * FROM users WHERE lower(username) = lower(?)",
               [body.username.strip()])
    if not u or not u["active"] or not check_password(body.password, u["password_hash"]):
        login_failed(key)
        db.audit(body.username, "login_failed", "", ip)
        raise HTTPException(401, "Wrong username or password")
    db.audit(u["username"], "login", "", ip)
    user = public_user(u)
    user["permissions"] = role_permissions(u["role"])
    return {"token": make_token(u["id"]), "user": user}


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
        audit(user, "password_change")
    return {"ok": True}


# ====================================================================== branding (public read)
LOGO_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".webp": "image/webp"}


def _logo_file() -> Path | None:
    for ext in LOGO_TYPES:
        p = config.BRANDING_DIR / f"logo{ext}"
        if p.exists():
            return p
    return None


@router.get("/branding")
def get_branding():
    s = db.get_settings()
    logo = _logo_file()
    return {"app_name": s["app_name"], "primary_color": s["primary_color"],
            "logo_url": f"/api/branding/logo?v={int(logo.stat().st_mtime)}" if logo else None}


@router.get("/branding/logo")
def get_logo():
    logo = _logo_file()
    if not logo:
        raise HTTPException(404, "No logo")
    return FileResponse(logo, media_type=LOGO_TYPES[logo.suffix],
                        headers={"Cache-Control": "public, max-age=86400"})


class BrandingIn(BaseModel):
    app_name: str = Field(min_length=1, max_length=60)
    primary_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


@router.put("/branding")
def put_branding(body: BrandingIn, user: dict = Depends(require("settings"))):
    db.save_settings(body.model_dump())
    audit(user, "branding_update", f"name={body.app_name} color={body.primary_color}")
    return get_branding()


@router.post("/branding/logo")
def upload_logo(file: UploadFile = File(...), user: dict = Depends(require("settings"))):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in LOGO_TYPES:
        raise HTTPException(400, "Logo must be PNG, JPG or WEBP")
    data = file.file.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(400, "Logo must be smaller than 2 MB")
    old = _logo_file()
    if old:
        old.unlink()
    (config.BRANDING_DIR / f"logo{ext}").write_bytes(data)
    audit(user, "branding_logo", file.filename or "")
    return get_branding()


@router.delete("/branding/logo")
def delete_logo(user: dict = Depends(require("settings"))):
    old = _logo_file()
    if old:
        old.unlink()
    audit(user, "branding_logo_removed")
    return get_branding()


# ====================================================================== meta & settings
@router.get("/meta")
def get_meta(user: dict = Depends(current_user)):
    m = db.cached(("meta", tuple(user["branches"])), lambda: an.meta(user["branches"] or None))
    last = db.one(db.cursor(), "SELECT id, filename, finished_at FROM imports WHERE status='done' "
                               "ORDER BY id DESC LIMIT 1")
    s = db.public_settings()
    return {**m, "last_import": last, "settings": s, "segments": an.SEGMENTS,
            "ai_enabled": s["openai_key_set"]}


class SettingsIn(BaseModel):
    active_days: int = Field(ge=1)
    attention_days: int = Field(ge=1)
    high_value_spend: float = Field(ge=0)
    loyalty_spend: float = Field(ge=0)
    loyalty_visits: int = Field(ge=1)
    openai_model: str | None = None
    openai_api_key: str | None = None   # "" removes it, None keeps it


@router.get("/settings")
def get_settings(user: dict = Depends(current_user)):
    return db.public_settings()


@router.put("/settings")
def put_settings(body: SettingsIn, user: dict = Depends(require("settings"))):
    if body.attention_days <= body.active_days:
        raise HTTPException(400, "'Needs attention' days must be greater than 'Active' days")
    values = body.model_dump(exclude_none=True)
    if body.openai_api_key is not None:
        values["openai_api_key"] = body.openai_api_key.strip()
    db.save_settings(values)
    changed = {k: v for k, v in values.items() if k != "openai_api_key"}
    if "openai_api_key" in values:
        changed["openai_api_key"] = "updated" if values["openai_api_key"] else "removed"
    audit(user, "settings_update", json.dumps(changed))
    return db.public_settings()


# ====================================================================== dashboard
@router.get("/summary")
def get_summary(f: an.Filters = Depends(filters), export: bool = False, lang: str = "en",
                user: dict = Depends(require("dashboard"))):
    res = db.cached(("summary", f.key()), lambda: an.summary(f, db.get_settings()))
    if not export:
        return res
    need_export(user)
    audit(user, "export", f"summary report {filter_text(f)}")
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
        ("شهري" if ar else "Monthly",
         ex.frame(res["monthly"], ["month", "sales", "customers", "invoices"], lang)),
        ("الفروع" if ar else "Branches",
         ex.frame(res["by_branch"], ["branch", "sales", "customers", "invoices",
                                     "avg_per_customer"], lang)),
        ("نوع البيع" if ar else "Sales types",
         ex.frame(res["by_type"], ["sales_type", "sales", "invoices"], lang)),
        ("المواسم" if ar else "Seasons",
         ex.frame(res["by_season"], ["season", "sales", "invoices"], lang)),
        ("أفضل الأصناف" if ar else "Top items",
         ex.frame(res["top_items"], ["item", "sales", "quantity", "customers"], lang)),
    ]
    title = "تقرير الملخص العام" if ar else "Overall Summary Report"
    return xlsx_response(ex.workbook(sheets, lang, title, filter_meta(f, lang)),
                         "summary_report.xlsx")


@router.get("/insights")
def get_insights(f: an.Filters = Depends(filters), export: bool = False, lang: str = "en",
                 user: dict = Depends(require("insights"))):
    res = db.cached(("insights", f.key()), lambda: an.insights(f, db.get_settings()))
    if not export:
        return res
    need_export(user)
    audit(user, "export", f"insights report {filter_text(f)}")
    ar = lang == "ar"
    cohort_rows = [{"cohort": c["cohort"], "size": c["size"],
                    **{f"M{x['k']}": x["pct"] for x in c["retention"]}} for c in res["cohorts"]]
    sheets = [
        ("التنبيهات" if ar else "Alerts",
         pd.DataFrame([[a["ar" if ar else "en"]] for a in res["alerts"]],
                      columns=["التنبيه" if ar else "Alert"])),
        ("شرائح RFM" if ar else "RFM segments",
         ex.frame(res["rfm"], ["segment", "customers", "sales", "share", "avg_spend",
                               "avg_visits", "avg_days_since"], lang)),
        ("خطر الفقد" if ar else "Churn risk",
         ex.frame(res["churn"], ["churn_risk", "customers", "sales"], lang)),
        ("نمو الفروع" if ar else "Branch growth",
         ex.frame(res["branch_growth"], ["branch", "sales", "prev_sales", "sales_change",
                                         "customers", "prev_customers", "customers_change"], lang)),
        ("يشترى معاً" if ar else "Bought together",
         ex.frame(res["basket"], ["item_a", "item_b", "together", "confidence_a_b",
                                  "confidence_b_a", "lift"], lang)),
        ("جديد ومتكرر" if ar else "New vs returning",
         ex.frame(res["new_vs_returning"], ["month", "new", "returning"], lang)),
        ("الاحتفاظ" if ar else "Cohort retention", pd.DataFrame(cohort_rows)),
    ]
    title = "تقرير التحليلات الذكية" if ar else "Smart Insights Report"
    return xlsx_response(ex.workbook(sheets, lang, title, filter_meta(f, lang)),
                         "insights_report.xlsx")


# ====================================================================== customers
CUSTOMER_VIEWS = {
    "customers": ["phone", "name", "branch", "district", "total_spent", "visits", "avg_per_visit",
                  "max_invoice", "min_invoice", "items_count", "fav_item", "first_visit",
                  "last_visit", "days_since", "avg_days_between", "top_sales_type", "segment",
                  "status"],
    "business": ["phone", "name", "branch", "total_spent", "visits", "top_material",
                 "top_category", "top_sales_type", "top_season", "loyal"],
    "recommendations": ["phone", "name", "branch", "total_spent", "visits", "last_visit",
                        "days_since", "expected_next", "overdue_days", "churn_risk", "segment",
                        "status", "high_value", "action"],
}
VIEW_PERMS = {"customers": "customers", "business": "business",
              "recommendations": "recommendations"}


@router.get("/customers")
def get_customers(
    f: an.Filters = Depends(filters),
    user: dict = Depends(current_user),
    q: str | None = None,
    status: list[str] = Query(default=[]),
    segment: list[str] = Query(default=[]),
    churn: list[str] = Query(default=[]),
    flag: Literal["high_value", "loyal", "invalid_phone", "multi_branch", "due_soon",
                  "overdue"] | None = None,
    sort: str = "priority",
    desc: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    export: bool = False,
    view: Literal["customers", "business", "recommendations"] = "customers",
    lang: str = "en",
):
    if VIEW_PERMS[view] not in user["permissions"]:
        raise HTTPException(403, "You don't have access to this")
    if export:
        need_export(user)

    def run():
        return an.list_customers(f, db.get_settings(), q=q, status=status, flag=flag,
                                 segment=segment, churn=churn, sort=sort, desc=desc, page=page,
                                 page_size=page_size, limit_all=export)

    res = run() if export else db.cached(
        ("customers", f.key(), q, tuple(status), tuple(segment), tuple(churn), flag, sort, desc,
         page, page_size), run)
    res = {**res, "rows": [dict(r) for r in res["rows"]]}
    for r in res["rows"]:
        r["action"] = ex.ACTIONS.get(r["status"])
    protect(res["rows"], user)
    if not export:
        return res
    audit(user, "export", f"{view} list ({res['total']} customers) {filter_text(f)}")
    cols = CUSTOMER_VIEWS[view]
    names = {"customers": ("Customers", "العملاء"), "business": ("Business", "تحليل الأعمال"),
             "recommendations": ("Recommendations", "التوصيات")}[view]
    sheet = names[1] if lang == "ar" else names[0]
    content = ex.workbook([(sheet, ex.frame(res["rows"], cols, lang))], lang, sheet,
                          filter_meta(f, lang))
    return xlsx_response(content, f"{view}_{date.today().isoformat()}.xlsx")


@router.get("/customer-totals")
def get_customer_totals(f: an.Filters = Depends(filters), user: dict = Depends(require("customers"))):
    """How many customers / invoices / sales match the filters, split by sales type."""
    return db.cached(("filter_totals", f.key()), lambda: an.filter_totals(f))


@router.get("/customers/{cid}")
def get_customer(cid: str, f: an.Filters = Depends(filters), export: bool = False,
                 lang: str = "en", user: dict = Depends(require("customers"))):
    phone = an.phone_for_cid(cid)
    res = an.customer_profile(phone, f, db.get_settings()) if phone else None
    if not res:
        raise HTTPException(404, "Customer not found")
    s = res["summary"]
    s["action"] = ex.ACTIONS.get(s["status"])
    audit(user, "view_customer", f"{mask_phone(phone)} {s.get('name') or ''}")
    protect([s], user)
    if not export:
        return res
    need_export(user)
    audit(user, "export", f"customer profile {mask_phone(phone)}")
    info_cols = CUSTOMER_VIEWS["customers"] + ["top_material", "top_category", "top_season",
                                                "loyal", "high_value", "churn_risk",
                                                "expected_next", "action"]
    info = ex.frame([s], info_cols, lang).T.reset_index()
    info.columns = [ex.label("metric", lang), ex.label("value", lang)]
    ar = lang == "ar"
    sheets = [
        ("العميل" if ar else "Customer", info),
        ("الزيارات" if ar else "Visits",
         ex.frame(res["visits"], ["date", "branch", "sales_type", "lines", "total", "items"], lang)),
        ("الأصناف" if ar else "Items",
         ex.frame(res["top_items"], ["item", "quantity", "sales", "times"], lang)),
        ("شهري" if ar else "Monthly", ex.frame(res["monthly"], ["month", "sales", "visits"], lang)),
    ]
    return xlsx_response(ex.workbook(sheets, lang), f"customer_{cid}.xlsx")


# ====================================================================== customer base
@router.get("/directory/summary")
def get_directory_summary(user: dict = Depends(require("customers"))):
    return db.cached(("dir_summary", tuple(user["branches"])),
                     lambda: an.directory_summary(user["branches"] or None))


@router.get("/directory")
def get_directory(user: dict = Depends(require("customers")), q: str | None = None,
                  region: list[str] = Query(default=[]), city: list[str] = Query(default=[]),
                  district: list[str] = Query(default=[]), bought: bool | None = None,
                  invalid: bool = False, sort: str = "name", desc: bool = False,
                  page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                  export: bool = False, lang: str = "en"):
    if export:
        need_export(user)
    res = an.directory_list(user["branches"] or None, q=q, region=region, city=city,
                            district=district, bought=bought, invalid=invalid, sort=sort,
                            desc=desc, page=page, page_size=page_size, limit_all=export)
    protect(res["rows"], user)
    if not export:
        return res
    audit(user, "export", f"customer list ({res['total']} customers)")
    cols = ["phone", "name", "region", "city", "district", "area", "address", "email",
            "phone_valid", "bought", "total_spent", "visits", "last_visit"]
    sheet = "قاعدة العملاء" if lang == "ar" else "Customer base"
    return xlsx_response(ex.workbook([(sheet, ex.frame(res["rows"], cols, lang))], lang, sheet),
                         "customer_base.xlsx")


# ====================================================================== products
@router.get("/products")
def get_products(f: an.Filters = Depends(filters), q: str | None = None, sort: str = "sales",
                 desc: bool = True, page: int = Query(1, ge=1),
                 page_size: int = Query(50, ge=1, le=500), export: bool = False,
                 lang: str = "en", user: dict = Depends(require("business"))):
    if export:
        need_export(user)
        res = an.products(f, q=q, sort=sort, desc=desc, limit_all=True)
        audit(user, "export", f"products ({res['total']}) {filter_text(f)}")
        cols = ["item", "code", "category", "material_group", "sales", "share", "quantity",
                "invoices", "customers", "repeat_buyers", "repeat_rate", "times_per_buyer",
                "avg_price", "top_branch", "first_sold", "last_sold"]
        sheet = "الأصناف" if lang == "ar" else "Products"
        return xlsx_response(ex.workbook([(sheet, ex.frame(res["rows"], cols, lang))], lang, sheet,
                                         filter_meta(f, lang)), "products_report.xlsx")
    return db.cached(("products", f.key(), q, sort, desc, page, page_size),
                     lambda: an.products(f, q=q, sort=sort, desc=desc, page=page,
                                         page_size=page_size))


# ====================================================================== area
@router.get("/area")
def get_area(f: an.Filters = Depends(filters), min_customers: int = Query(5, ge=1),
             export: bool = False, lang: str = "en", user: dict = Depends(require("area"))):
    res = db.cached(("area", f.key(), min_customers), lambda: an.area(f, min_customers))
    if not export:
        return res
    need_export(user)
    audit(user, "export", f"area report {filter_text(f)}")
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
              export: bool = False, lang: str = "en",
              user: dict = Depends(require("transactions"))):
    if export:
        need_export(user)
    res = an.list_sales(f, q=q, sort=sort, desc=desc, page=page, page_size=page_size,
                        limit_all=export)
    protect(res["rows"], user)
    if not export:
        return res
    audit(user, "export", f"transactions ({res['total']} rows) {filter_text(f)}")
    sheet = "المبيعات" if lang == "ar" else "Transactions"
    return xlsx_response(ex.workbook([(sheet, ex.frame(res["rows"], an.SALES_COLUMNS, lang))],
                                     lang, sheet, filter_meta(f, lang)),
                         f"transactions_{date.today().isoformat()}.xlsx")


# ====================================================================== AI analyst
class AskIn(BaseModel):
    question: str = Field(default="", max_length=4000)
    history: list[dict] = []
    report: bool = False
    lang: Literal["en", "ar"] = "en"


@router.post("/ai/ask")
def ai_ask(body: AskIn, f: an.Filters = Depends(filters), user: dict = Depends(require("ai"))):
    if not body.report and not body.question.strip():
        raise HTTPException(400, "Please type a question")
    audit(user, "ai_report" if body.report else "ai_question",
          f"{body.question[:300]} | {filter_text(f)}")
    try:
        return ai.ask(body.question, body.history, f, db.get_settings(), body.lang, body.report)
    except ai.AIError as e:
        raise HTTPException(400, str(e)) from e


# ====================================================================== imports (chunked upload)
UPLOAD_SUFFIXES = (".xlsx", ".xlsm", ".xls", ".xlsb", ".csv", ".zip")
_uploads: dict[str, dict] = {}


class UploadInit(BaseModel):
    filename: str
    size: int = Field(ge=1)


@router.post("/imports/uploads")
def upload_init(body: UploadInit, user: dict = Depends(require("import"))):
    suffix = Path(body.filename).suffix.lower()
    if suffix not in UPLOAD_SUFFIXES:
        raise HTTPException(400, "Please upload Excel (.xlsx .xls .xlsb), CSV, or a .zip of them")
    if body.size > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"File is larger than {config.MAX_UPLOAD_MB} MB")
    uid = uuid.uuid4().hex
    path = config.UPLOAD_DIR / f"{uid}{suffix}"
    path.touch()
    _uploads[uid] = {"path": path, "filename": body.filename, "size": body.size,
                     "received": 0, "user": user["username"]}
    return {"upload_id": uid, "chunk_size": 8 * 1024 * 1024}


def _get_upload(uid: str) -> dict:
    up = _uploads.get(uid)
    if not up or not up["path"].exists():
        raise HTTPException(404, "Upload not found or expired, please upload again")
    return up


@router.get("/imports/uploads/{uid}")
def upload_status(uid: str, user: dict = Depends(require("import"))):
    up = _get_upload(uid)
    return {"received": up["received"], "size": up["size"]}


@router.put("/imports/uploads/{uid}")
async def upload_chunk(uid: str, request: Request, offset: int = Query(ge=0),
                       user: dict = Depends(require("import"))):
    up = _get_upload(uid)
    if offset != up["received"]:  # resume support: client re-sends from `received`
        raise HTTPException(409, f"Expected offset {up['received']}")
    n = 0
    with up["path"].open("ab") as fh:
        async for block in request.stream():
            fh.write(block)
            n += len(block)
    up["received"] += n
    if up["received"] > up["size"]:
        raise HTTPException(400, "Received more data than announced")
    return {"received": up["received"]}


def _do_preview(up: dict, sheet: str | None):
    try:
        pv = importer.preview(up["path"], sheet)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not read the file: {e}") from e
    up["columns"] = pv["columns"]
    up["sheet"] = pv["sheet"]
    up.setdefault("sheet_columns", {}).update({x["sheet"]: x["columns"] for x in pv["sheets_info"]})
    return pv


@router.post("/imports/uploads/{uid}/finish")
def upload_finish(uid: str, user: dict = Depends(require("import"))):
    up = _get_upload(uid)
    if up["received"] != up["size"]:
        raise HTTPException(400, "Upload is not complete yet")
    try:
        up["path"] = importer.unpack(up["path"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not open the zip file: {e}") from e
    up["hash"] = importer.file_sha256(up["path"])
    dup = db.one(db.cursor(), "SELECT id, filename, finished_at FROM imports "
                              "WHERE file_hash = ? AND status = 'done' ORDER BY id DESC LIMIT 1",
                 [up["hash"]])
    pv = _do_preview(up, None)
    audit(user, "import_upload", f"{up['filename']} ({up['size'] / 1e6:.1f} MB)")
    return {"upload_id": uid, "filename": up["filename"], **pv, "duplicate_of": dup}


@router.get("/imports/uploads/{uid}/preview")
def upload_preview(uid: str, sheet: str, user: dict = Depends(require("import"))):
    up = _get_upload(uid)
    return _do_preview(up, sheet)


class ImportJob(BaseModel):
    sheet: str | None = None
    kind: Literal["sales", "customers"] = "sales"
    mapping: dict[str, str | None]
    mode: Literal["merge", "replace_period", "append_new", "replace_all", "upsert"] = "merge"


class CommitIn(BaseModel):
    upload_id: str
    # several sheets of one workbook, each with its own kind and columns ...
    jobs: list[ImportJob] | None = None
    # ... or a single sheet (older clients)
    kind: Literal["sales", "customers"] = "sales"
    mapping: dict[str, str | None] | None = None
    mode: Literal["merge", "replace_period", "append_new", "replace_all", "upsert"] = "merge"
    sheet: str | None = None
    remember_mapping: bool = True


def _check_job(j: ImportJob) -> dict:
    fields, required, modes = (
        (FIELDS, REQUIRED_FIELDS, importer.IMPORT_MODES) if j.kind == "sales"
        else (CUSTOMER_FIELDS, CUSTOMER_REQUIRED, importer.CUSTOMER_MODES))
    where = f" (sheet '{j.sheet}')" if j.sheet else ""
    if j.mode not in modes:
        raise HTTPException(400, f"Mode must be one of: {', '.join(modes)}{where}")
    mapping = {f: (j.mapping.get(f) or None) for f in fields}
    missing = [f for f in required if not mapping[f]]
    if missing:
        raise HTTPException(400, f"Please choose a column for: {', '.join(missing)}{where}")
    return mapping


@router.post("/imports/commit")
def commit(body: CommitIn, user: dict = Depends(require("import"))):
    up = _get_upload(body.upload_id)
    if "columns" not in up:
        raise HTTPException(400, "Finish the upload first")
    jobs = body.jobs or [ImportJob(sheet=body.sheet or up.get("sheet"), kind=body.kind,
                                   mapping=body.mapping or {}, mode=body.mode)]
    if not jobs:
        raise HTTPException(400, "Choose at least one sheet to import")
    checked = [(j, _check_job(j)) for j in jobs]
    _uploads.pop(body.upload_id, None)
    cur = db.cursor()
    run = []
    for j, mapping in checked:
        cols = up.get("sheet_columns", {}).get(j.sheet, up["columns"])
        if body.remember_mapping:
            cur.execute("INSERT INTO saved_mappings VALUES (?, ?) ON CONFLICT (signature) "
                        "DO UPDATE SET mapping = EXCLUDED.mapping",
                        [importer.header_signature(cols, j.kind), json.dumps(mapping)])
        name = up["filename"] + (f" [{j.sheet}]" if j.sheet and len(jobs) > 1 else "")
        imp_id = cur.execute(
            "INSERT INTO imports (filename, kind, mode, status, stage, mapping, created_by, sheet, "
            "file_hash, file_size) VALUES (?, ?, ?, 'running', 'queued', ?, ?, ?, ?, ?) RETURNING id",
            [name, j.kind, j.mode, json.dumps(mapping), user["username"], j.sheet,
             up.get("hash"), up["size"]]).fetchone()[0]
        audit(user, "import_start", f"#{imp_id} {name} kind={j.kind} mode={j.mode}")
        run.append({"import_id": imp_id, "kind": j.kind, "mapping": mapping, "mode": j.mode,
                    "sheet": j.sheet})
    threading.Thread(target=importer.run_jobs, args=(run, up["path"]), daemon=True).start()
    return {"import_ids": [r["import_id"] for r in run], "import_id": run[0]["import_id"]}


@router.get("/imports")
def list_imports(user: dict = Depends(require("import"))):
    return db.rows(db.cursor(), "SELECT id, filename, kind, mode, status, stage, progress, message, "
                                "sheet, file_size, rows_read, rows_imported, rows_skipped, "
                                "rows_replaced, invalid_phones, invalid_dates, date_from, date_to, "
                                "created_by, created_at, finished_at "
                                "FROM imports ORDER BY id DESC LIMIT 100")


@router.get("/imports/{imp_id}")
def get_import(imp_id: int, user: dict = Depends(require("import"))):
    r = db.one(db.cursor(), "SELECT * FROM imports WHERE id = ?", [imp_id])
    if not r:
        raise HTTPException(404, "Import not found")
    return r


@router.post("/imports/{imp_id}/cancel")
def cancel_import(imp_id: int, user: dict = Depends(require("import"))):
    cur = db.cursor()
    row = db.one(cur, "SELECT status, stage FROM imports WHERE id = ?", [imp_id])
    if not row or row["status"] != "running":
        raise HTTPException(400, "This import is not running")
    importer.cancel(imp_id)
    if row["stage"] == "queued":  # not started yet: mark it right away
        cur.execute("UPDATE imports SET status='failed', message='Cancelled by user', "
                    "finished_at=now() WHERE id = ?", [imp_id])
    audit(user, "import_cancel", f"#{imp_id}")
    return {"ok": True}


@router.delete("/imports/{imp_id}")
def delete_import(imp_id: int, user: dict = Depends(require("import"))):
    cur = db.cursor()
    imp = db.one(cur, "SELECT kind FROM imports WHERE id = ?", [imp_id])
    table = "customer_directory" if imp and imp["kind"] == "customers" else "sales"
    n = cur.execute(f"SELECT count(*) FROM {table} WHERE import_id = ?", [imp_id]).fetchone()[0]
    cur.execute(f"DELETE FROM {table} WHERE import_id = ?", [imp_id])
    cur.execute("UPDATE imports SET status='deleted', message=? WHERE id = ?",
                [f"{n} rows removed", imp_id])
    db.bump_version()
    audit(user, "import_delete", f"#{imp_id} ({n} rows)")
    return {"deleted_rows": n}


@router.get("/maintenance/duplicates")
def check_duplicates(user: dict = Depends(require("import"))):
    """Lines stored twice by different imports (e.g. overlapping reports)."""
    return importer.find_duplicates(db.cursor())


@router.delete("/maintenance/duplicates")
def delete_duplicates(user: dict = Depends(require("import"))):
    with importer._import_lock:  # never while an import is running
        n = importer.remove_duplicates(db.connection())
    audit(user, "duplicates_removed", f"{n} duplicate sales lines removed")
    return {"removed": n}


@router.get("/maintenance/data-check")
def get_data_check(user: dict = Depends(require("import"))):
    """Live numbers straight from the database (never cached)."""
    res = an.data_check()
    res["checked_at"] = datetime.now()
    res["cache_version"] = db._version
    return res


@router.post("/maintenance/refresh")
def refresh_analytics(user: dict = Depends(require("import"))):
    """Throw away all cached results: every page recalculates from the database."""
    db.bump_version()
    audit(user, "analytics_refresh")
    return {"ok": True}


def cleanup_stale_uploads():
    """Remove half-finished uploads older than a day (called at startup)."""
    limit = datetime.now().timestamp() - 86400
    for p in config.UPLOAD_DIR.glob("*"):
        if p.stat().st_mtime < limit:
            p.unlink(missing_ok=True) if p.is_file() else shutil.rmtree(p, ignore_errors=True)


# ====================================================================== users & roles
class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.@-]+$")
    full_name: str | None = None
    role: str = "manager"
    branches: list[str] = []
    language: Literal["en", "ar"] = "en"
    active: bool = True
    password: str | None = Field(default=None, min_length=8)


def _role_exists(name: str) -> bool:
    return bool(db.one(db.cursor(), "SELECT name FROM roles WHERE name = ?", [name]))


@router.get("/users")
def list_users(user: dict = Depends(require("users"))):
    return [public_user(u) for u in db.rows(db.cursor(), "SELECT * FROM users ORDER BY id")]


@router.post("/users")
def create_user(body: UserIn, user: dict = Depends(require("users"))):
    if not body.password:
        raise HTTPException(400, "Password is required (8+ characters)")
    if not _role_exists(body.role):
        raise HTTPException(400, "Unknown role")
    cur = db.cursor()
    if db.one(cur, "SELECT id FROM users WHERE lower(username) = lower(?)", [body.username]):
        raise HTTPException(400, "Username already exists")
    cur.execute(
        "INSERT INTO users (username, password_hash, full_name, role, branches, language, active) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [body.username.strip(), hash_password(body.password), body.full_name, body.role,
         json.dumps(body.branches), body.language, body.active])
    audit(user, "user_create", f"{body.username} role={body.role} branches={body.branches or 'all'}")
    return {"ok": True}


@router.put("/users/{uid}")
def update_user(uid: int, body: UserIn, user: dict = Depends(require("users"))):
    cur = db.cursor()
    old = db.one(cur, "SELECT * FROM users WHERE id = ?", [uid])
    if not old:
        raise HTTPException(404, "User not found")
    if not _role_exists(body.role):
        raise HTTPException(400, "Unknown role")
    if uid == user["id"] and (body.role != "admin" and old["role"] == "admin" or not body.active):
        raise HTTPException(400, "You cannot remove your own admin access")
    if db.one(cur, "SELECT id FROM users WHERE lower(username) = lower(?) AND id <> ?",
              [body.username, uid]):
        raise HTTPException(400, "Username already exists")
    cur.execute(
        "UPDATE users SET username=?, full_name=?, role=?, branches=?, language=?, active=? "
        "WHERE id=?",
        [body.username.strip(), body.full_name, body.role, json.dumps(body.branches),
         body.language, body.active, uid])
    if body.password:
        cur.execute("UPDATE users SET password_hash=? WHERE id=?",
                    [hash_password(body.password), uid])
    changes = [f"{k}: {old[k]} -> {v}" for k, v in
               (("role", body.role), ("active", body.active), ("username", body.username))
               if str(old[k]) != str(v)]
    if json.loads(old["branches"] or "[]") != body.branches:
        changes.append(f"branches -> {body.branches or 'all'}")
    if body.password:
        changes.append("password reset")
    audit(user, "user_update", f"{old['username']}: " + ("; ".join(changes) or "no change"))
    return {"ok": True}


@router.delete("/users/{uid}")
def delete_user(uid: int, user: dict = Depends(require("users"))):
    if uid == user["id"]:
        raise HTTPException(400, "You cannot delete yourself")
    cur = db.cursor()
    old = db.one(cur, "SELECT username FROM users WHERE id = ?", [uid])
    cur.execute("DELETE FROM users WHERE id = ?", [uid])
    audit(user, "user_delete", old["username"] if old else str(uid))
    return {"ok": True}


class RoleIn(BaseModel):
    name: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9_]+$")
    description: str | None = None
    permissions: list[str] = []


@router.get("/roles")
def list_roles(user: dict = Depends(require("users"))):
    roles = db.rows(db.cursor(), """SELECT r.name, r.description, r.permissions, r.builtin,
        (SELECT count(*) FROM users u WHERE u.role = r.name) AS users
        FROM roles r ORDER BY r.builtin DESC, r.name""")
    for r in roles:
        r["permissions"] = json.loads(r["permissions"])
    return {"roles": roles,
            "permissions": [{"key": k, "en": en, "ar": ar} for k, en, ar in PERMISSIONS]}


def _clean_perms(perms: list[str]) -> list[str]:
    return [p for p in ALL_PERMISSIONS if p in perms]


@router.post("/roles")
def create_role(body: RoleIn, user: dict = Depends(require("users"))):
    if _role_exists(body.name):
        raise HTTPException(400, "Role already exists")
    db.cursor().execute("INSERT INTO roles VALUES (?, ?, ?, FALSE)",
                        [body.name, body.description, json.dumps(_clean_perms(body.permissions))])
    audit(user, "role_create", f"{body.name}: {', '.join(_clean_perms(body.permissions))}")
    return {"ok": True}


@router.put("/roles/{name}")
def update_role(name: str, body: RoleIn, user: dict = Depends(require("users"))):
    if name == "admin":
        raise HTTPException(400, "The admin role always has full access")
    old = db.one(db.cursor(), "SELECT permissions FROM roles WHERE name = ?", [name])
    if not old:
        raise HTTPException(404, "Role not found")
    perms = _clean_perms(body.permissions)
    db.cursor().execute("UPDATE roles SET description = ?, permissions = ? WHERE name = ?",
                        [body.description, json.dumps(perms), name])
    before = set(json.loads(old["permissions"]))
    added, removed = set(perms) - before, before - set(perms)
    audit(user, "role_update", f"{name}: +{sorted(added) or '-'} -{sorted(removed) or '-'}")
    return {"ok": True}


@router.delete("/roles/{name}")
def delete_role(name: str, user: dict = Depends(require("users"))):
    if name == "admin":
        raise HTTPException(400, "The admin role cannot be deleted")
    cur = db.cursor()
    if cur.execute("SELECT count(*) FROM users WHERE role = ?", [name]).fetchone()[0]:
        raise HTTPException(400, "Move the users of this role to another role first")
    cur.execute("DELETE FROM roles WHERE name = ?", [name])
    audit(user, "role_delete", name)
    return {"ok": True}


# ====================================================================== audit log
@router.get("/audit")
def get_audit(user: dict = Depends(require("audit")), username: str | None = None,
              action: str | None = None, q: str | None = None,
              date_from: date | None = None, date_to: date | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
              export: bool = False, lang: str = "en"):
    conds, p = ["TRUE"], []
    if username:
        conds.append("username = ?")
        p.append(username)
    if action:
        conds.append("action = ?")
        p.append(action)
    if q:
        conds.append("(details ILIKE ? OR username ILIKE ?)")
        p += [f"%{q}%", f"%{q}%"]
    if date_from:
        conds.append("ts >= ?")
        p.append(date_from)
    if date_to:
        conds.append("ts < ?")
        p.append(date_to + timedelta(days=1))
    w = " AND ".join(conds)
    cur = db.cursor()
    total = cur.execute(f"SELECT count(*) FROM audit_log WHERE {w}", p).fetchone()[0]
    limit = "LIMIT 1048000" if export else f"LIMIT {page_size} OFFSET {(page - 1) * page_size}"
    rows = db.rows(cur, f"SELECT id, ts, username, action, details, ip FROM audit_log "
                        f"WHERE {w} ORDER BY id DESC {limit}", p)
    if not export:
        actions = [r[0] for r in cur.execute(
            "SELECT DISTINCT action FROM audit_log ORDER BY 1").fetchall()]
        return {"rows": rows, "total": total, "actions": actions}
    need_export(user)
    audit(user, "export", f"audit log ({total} rows)")
    df = pd.DataFrame(rows, columns=["id", "ts", "username", "action", "details", "ip"])
    return xlsx_response(ex.workbook([("Audit", df)], lang), "audit_log.xlsx")



# ====================================================================== POS API keys
class ApiKeyIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    branch: str | None = Field(default=None, max_length=150)


@router.get("/integration/keys")
def list_api_keys(user: dict = Depends(require("settings"))):
    return db.rows(db.cursor(), "SELECT id, name, branch, prefix, active, created_by, created_at, "
                                "last_used_at, requests FROM api_keys ORDER BY id DESC")


@router.post("/integration/keys")
def create_api_key(body: ApiKeyIn, user: dict = Depends(require("settings"))):
    from .pos import hash_key, new_key
    key = new_key()
    db.cursor().execute(
        "INSERT INTO api_keys (name, branch, prefix, key_hash, created_by) VALUES (?, ?, ?, ?, ?)",
        [body.name.strip(), (body.branch or "").strip() or None, key[:10], hash_key(key),
         user["username"]])
    audit(user, "api_key_create", f"{body.name} branch={body.branch or '-'} {key[:10]}…")
    return {"key": key, "note": "Copy it now - it is shown only once."}


@router.delete("/integration/keys/{kid}")
def revoke_api_key(kid: int, user: dict = Depends(require("settings"))):
    cur = db.cursor()
    row = db.one(cur, "SELECT name, prefix FROM api_keys WHERE id = ?", [kid])
    cur.execute("UPDATE api_keys SET active = FALSE WHERE id = ?", [kid])
    audit(user, "api_key_revoke", f"{row['name']} {row['prefix']}…" if row else str(kid))
    return {"ok": True}


@router.get("/integration/activity")
def pos_activity(user: dict = Depends(require("settings"))):
    """Live feed summary: what each branch sent through the POS API."""
    cur = db.cursor()
    return {
        "branches": db.rows(cur, """SELECT branch, count(DISTINCT ext_key) AS invoices,
            max(invoice_date) AS last_invoice, {} AS sales FROM sales WHERE source = 'pos'
            GROUP BY branch ORDER BY branch""".format(an.R("sum(item_price)"))),
        "customers": db.one(cur, """SELECT count(*) AS total,
            count(*) FILTER (WHERE registered_at >= now() - interval '1 day') AS last_24h,
            max(updated_at) AS last_update FROM customer_directory WHERE source = 'pos'"""),
    }


# ====================================================================== live POS
@router.get("/live")
def get_live(branch: str | None = None, user: dict = Depends(require("dashboard"))):
    res = an.live(user["branches"] or None, branch)
    protect(res["feed"], user)
    protect(res["new_customers"], user)
    return res
