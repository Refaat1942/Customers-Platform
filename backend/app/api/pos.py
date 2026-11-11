"""POS integration API (v1): the branches' POS pushes customers and invoices here.

Authentication: header `X-API-Key: cpk_...` (one key per branch, created in Settings).
Everything is idempotent: sending the same customer or invoice again updates it, never duplicates.
Full guide for the POS developer: docs/POS_API.md
"""

import hashlib
import json
import secrets
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .. import db
from ..core.importer import SEASONS
from ..core.phone import is_valid_egy_mobile, normalize_egy_phone

router = APIRouter(prefix="/api/v1/pos", tags=["POS integration"])

CAIRO = ZoneInfo("Africa/Cairo")
MAX_INVOICES = 1000
MAX_CUSTOMERS = 5000


# ====================================================================== keys
def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    return "cpk_" + secrets.token_urlsafe(32)


def pos_client(request: Request, x_api_key: str | None = Header(default=None)) -> dict:
    key = x_api_key or (request.headers.get("authorization", "").removeprefix("Bearer ").strip()
                        if request.headers.get("authorization", "").startswith("Bearer cpk_") else None)
    if not key:
        raise HTTPException(401, "Missing X-API-Key header")
    cur = db.cursor()
    row = db.one(cur, "SELECT id, name, branch, active FROM api_keys WHERE key_hash = ?",
                 [hash_key(key)])
    if not row or not row["active"]:
        raise HTTPException(401, "Invalid or revoked API key")
    cur.execute("UPDATE api_keys SET last_used_at = now(), requests = requests + 1 WHERE id = ?",
                [row["id"]])
    return row


# ====================================================================== payloads
class PosCustomer(BaseModel):
    phone: str = Field(min_length=3, max_length=40, description="Mobile number in any format")
    name: str | None = Field(default=None, max_length=300)
    first_name: str | None = Field(default=None, max_length=150)
    last_name: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=200)
    gender: str | None = Field(default=None, max_length=20)
    birth_date: date | None = None
    region: str | None = Field(default=None, max_length=150, description="Governorate")
    city: str | None = Field(default=None, max_length=150)
    district: str | None = Field(default=None, max_length=150)
    area: str | None = Field(default=None, max_length=150)
    address: str | None = Field(default=None, max_length=1000)
    branch: str | None = Field(default=None, max_length=150,
                               description="Branch where the customer registered")
    registered_at: datetime | None = Field(default=None, description="Registration time in the POS")
    pos_customer_id: str | None = Field(default=None, max_length=100)
    extra: dict | None = Field(default=None, description="Any other fields (stored as JSON)")


class PosLine(BaseModel):
    item_code: str | None = Field(default=None, max_length=100)
    item_name: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=150)
    material_group: str | None = Field(default=None, max_length=150)
    quantity: float = 1
    unit: str | None = Field(default=None, max_length=50)
    unit_price: float | None = None
    discount: float = 0
    line_total: float | None = Field(default=None,
                                     description="Net amount of the line. Default: qty × price − discount")
    extra: dict | None = None


class PosInvoice(BaseModel):
    invoice_no: str = Field(min_length=1, max_length=100)
    branch: str | None = Field(default=None, max_length=150,
                               description="Defaults to the branch of the API key")
    invoice_date: datetime = Field(description="Date AND time of the invoice, e.g. 2026-11-11T14:35:00")
    status: Literal["completed", "return", "void"] = "completed"
    customer_phone: str | None = Field(default=None, max_length=40)
    customer_name: str | None = Field(default=None, max_length=300)
    customer_id: str | None = Field(default=None, max_length=100)
    sales_type: str | None = Field(default=None, max_length=100,
                                   description="Cash / Delivery / Insurance / ...")
    payment_method: str | None = Field(default=None, max_length=100)
    cashier: str | None = Field(default=None, max_length=150)
    lines: list[PosLine] = Field(default_factory=list, max_length=2000)
    extra: dict | None = None


class CustomersIn(BaseModel):
    customers: list[PosCustomer] = Field(max_length=MAX_CUSTOMERS)


class InvoicesIn(BaseModel):
    invoices: list[PosInvoice] = Field(max_length=MAX_INVOICES)


# ====================================================================== helpers
def _phone(raw: str | None) -> tuple[str | None, bool]:
    p = normalize_egy_phone(raw) if raw else ""
    return (p or None), is_valid_egy_mobile(p)


def _clean(v):
    return v.strip() or None if isinstance(v, str) else v


def upsert_customers(cur, customers: list[PosCustomer], default_branch: str | None) -> list[dict]:
    """Insert or update customers by phone; returns per-item errors."""
    errors, rows = [], {}
    for i, c in enumerate(customers):
        phone, valid = _phone(c.phone)
        if not phone:
            errors.append({"index": i, "phone": c.phone, "error": "phone has no digits"})
            continue
        first, last = _clean(c.first_name), _clean(c.last_name)
        name = _clean(c.name) or (" ".join(x for x in (first, last) if x) or None)
        rows[phone] = [phone, valid, name, first, last, _clean(c.address), _clean(c.region),
                       _clean(c.city), _clean(c.district), _clean(c.area), _clean(c.email),
                       _clean(c.gender), c.birth_date, c.registered_at,
                       _clean(c.branch) or default_branch, _clean(c.pos_customer_id), "pos",
                       json.dumps(c.extra, ensure_ascii=False, default=str) if c.extra else None]
    if rows:
        cols = ["phone", "phone_valid", "name", "first_name", "last_name", "address", "region",
                "city", "district", "area", "email", "gender", "birth_date", "registered_at",
                "registered_branch", "pos_customer_id", "source", "extra"]
        keep_first = {"registered_at", "registered_branch"}  # registration info never moves
        upd = ", ".join(
            f"{c} = coalesce(customer_directory.{c}, EXCLUDED.{c})" if c in keep_first
            else f"{c} = coalesce(EXCLUDED.{c}, customer_directory.{c})"
            for c in cols if c != "phone")
        ph = ", ".join(["?"] * len(cols))
        for r in rows.values():
            cur.execute(f"""INSERT INTO customer_directory ({', '.join(cols)}, updated_at)
                VALUES ({ph}, now()) ON CONFLICT (phone) DO UPDATE SET {upd}, updated_at = now()""",
                        r)
    return errors


SALES_COLS = ["phone", "phone_valid", "name", "branch", "district", "invoice_no", "visit_key",
              "invoice_date", "day", "season", "invoice_type", "item_code", "item_name",
              "material_group", "item_category", "quantity", "item_unit", "item_price", "source",
              "ext_key", "extra"]


def save_invoices(conn, invoices: list[PosInvoice], default_branch: str | None) -> dict:
    cur = db.Cursor(conn)
    errors, rows, keys, customers = [], [], [], []
    for i, inv in enumerate(invoices):
        branch = _clean(inv.branch) or default_branch
        if not branch:
            errors.append({"index": i, "invoice_no": inv.invoice_no,
                           "error": "branch is required (the API key has no default branch)"})
            continue
        if inv.status != "void" and not inv.lines:
            errors.append({"index": i, "invoice_no": inv.invoice_no, "error": "invoice has no lines"})
            continue
        ext_key = f"{branch}|{inv.invoice_no.strip()}"
        keys.append(ext_key)
        if inv.status == "void":
            continue  # a void just removes the invoice
        phone, valid = _phone(inv.customer_phone)
        if phone and inv.customer_name:
            customers.append(PosCustomer(phone=phone, name=inv.customer_name, branch=branch,
                                         pos_customer_id=inv.customer_id))
        sign = -1 if inv.status == "return" else 1
        ts = inv.invoice_date
        if ts.tzinfo:  # store everything in Cairo local time, like the Excel imports
            ts = ts.astimezone(CAIRO).replace(tzinfo=None)
        head = {k: v for k, v in (("payment_method", inv.payment_method), ("cashier", inv.cashier),
                                  ("customer_id", inv.customer_id), ("status", inv.status))
                if v}
        for ln in inv.lines:
            qty = abs(ln.quantity) * sign
            total = ln.line_total if ln.line_total is not None else \
                (abs(ln.quantity) * (ln.unit_price or 0) - (ln.discount or 0))
            extra = {**head, **({"unit_price": ln.unit_price} if ln.unit_price is not None else {}),
                     **({"discount": ln.discount} if ln.discount else {}),
                     **(ln.extra or {}), **(inv.extra or {})}
            rows.append([phone, valid, _clean(inv.customer_name), branch, None,
                         inv.invoice_no.strip(), ext_key, ts, ts.date(), SEASONS[ts.month],
                         "Return" if inv.status == "return" else _clean(inv.sales_type),
                         _clean(ln.item_code), _clean(ln.item_name), _clean(ln.material_group),
                         _clean(ln.category), qty, _clean(ln.unit), abs(total) * sign, "pos",
                         ext_key, json.dumps(extra, ensure_ascii=False, default=str) if extra else None])

    with conn.transaction():
        if customers:
            upsert_customers(cur, customers, None)
        if keys:  # re-sending an invoice replaces it (idempotent)
            cur.execute("DELETE FROM sales WHERE ext_key = ANY(?)", [keys])
        if rows:
            with cur.copy(f"COPY sales ({', '.join(SALES_COLS)}) FROM STDIN") as cp:
                for r in rows:
                    cp.write_row(r)
            cur.execute("""UPDATE sales s SET district = d.district, name = coalesce(s.name, d.name)
                           FROM customer_directory d
                           WHERE s.ext_key = ANY(?) AND s.phone = d.phone""", [keys])
            cur.execute("UPDATE sales SET district = 'Unknown' WHERE ext_key = ANY(?) "
                        "AND district IS NULL", [keys])
    return {"accepted": len(keys), "lines": len(rows), "rejected": errors}


# ====================================================================== endpoints
@router.get("/ping")
def ping(client: dict = Depends(pos_client)):
    """Check the connection and the API key."""
    return {"ok": True, "key": client["name"], "branch": client["branch"],
            "server_time": datetime.now().isoformat(timespec="seconds")}


@router.post("/customers")
def push_customers(body: CustomersIn, client: dict = Depends(pos_client)):
    """New or updated customers (up to 5000 per request). Matched by phone number."""
    conn = db.connection()
    cur = db.Cursor(conn)
    with conn.transaction():
        errors = upsert_customers(cur, body.customers, client["branch"])
        phones = [p for p in (_phone(c.phone)[0] for c in body.customers) if p]
        if phones:  # existing sales of these customers get their names / districts
            cur.execute("""UPDATE sales s SET district = d.district, name = coalesce(s.name, d.name)
                           FROM customer_directory d
                           WHERE s.phone = ANY(?) AND d.phone = s.phone AND d.district IS NOT NULL
                             AND s.district IS DISTINCT FROM d.district""", [phones])
    db.bump_version_soon()
    return {"accepted": len(body.customers) - len(errors), "rejected": errors}


@router.post("/invoices")
def push_invoices(body: InvoicesIn, client: dict = Depends(pos_client)):
    """Invoices with all their lines (up to 1000 per request). Matched by branch + invoice_no:
    sending the same invoice again replaces it; status 'void' deletes it; 'return' stores it
    with negative amounts."""
    res = save_invoices(db.connection(), body.invoices, client["branch"])
    db.bump_version_soon()
    return res


@router.delete("/invoices/{invoice_no}")
def void_invoice(invoice_no: str, branch: str | None = None,
                 client: dict = Depends(pos_client)):
    b = branch or client["branch"]
    if not b:
        raise HTTPException(400, "branch is required")
    cur = db.cursor()
    n = cur.execute("SELECT count(*) FROM sales WHERE ext_key = ?", [f"{b}|{invoice_no}"]).fetchone()[0]
    cur.execute("DELETE FROM sales WHERE ext_key = ?", [f"{b}|{invoice_no}"])
    db.bump_version_soon()
    return {"deleted_lines": n}


@router.get("/sync-state")
def sync_state(branch: str | None = Query(default=None), client: dict = Depends(pos_client)):
    """What the platform already has - the POS can resume sending from here after an outage."""
    b = branch or client["branch"]
    cur = db.cursor()
    cond, p = ("AND branch = ?", [b]) if b else ("", [])
    inv = db.one(cur, f"""SELECT count(DISTINCT ext_key) AS invoices, max(invoice_date) AS last_invoice_date
        FROM sales WHERE source = 'pos' {cond}""", p)
    cond2, p2 = ("AND registered_branch = ?", [b]) if b else ("", [])
    cus = db.one(cur, f"""SELECT count(*) AS customers, max(registered_at) AS last_registered_at,
        max(updated_at) AS last_update FROM customer_directory WHERE source = 'pos' {cond2}""", p2)
    return {"branch": b, **inv, **cus}
