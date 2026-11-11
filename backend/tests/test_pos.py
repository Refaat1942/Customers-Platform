import gzip
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def admin():
    from app import main
    with TestClient(main.app) as c:
        tok = c.post("/api/auth/login", json={"username": "admin", "password": "admin-pass-123"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        yield c


@pytest.fixture(scope="module")
def pos(admin):
    from app import main
    key = admin.post("/api/integration/keys", json={"name": "Maadi POS", "branch": "POS Maadi"}).json()["key"]
    c = TestClient(main.app)
    c.headers["X-API-Key"] = key
    c.key = key
    return c


INV = {"invoice_no": "M-1001", "invoice_date": "2026-11-10T14:35:00", "customer_phone": "+20 100 111 2222",
       "customer_name": "Sara Ali", "sales_type": "Cash", "cashier": "Mona", "payment_method": "Card",
       "lines": [{"item_code": "P1", "item_name": "Panadol", "category": "Medicine", "quantity": 2, "unit_price": 50},
                 {"item_code": "V1", "item_name": "Vitamin C", "quantity": 1, "unit_price": 120, "discount": 20}]}


def test_requires_key():
    from app import main
    c = TestClient(main.app)
    assert c.get("/api/v1/pos/ping").status_code == 401
    assert c.get("/api/v1/pos/ping", headers={"X-API-Key": "cpk_wrong"}).status_code == 401


def test_ping(pos):
    r = pos.get("/api/v1/pos/ping").json()
    assert r["ok"] and r["branch"] == "POS Maadi"


def test_customers_and_invoices(pos, admin):
    r = pos.post("/api/v1/pos/customers", json={"customers": [
        {"phone": "01001112222", "first_name": "Sara", "last_name": "Ali", "city": "Cairo",
         "district": "Maadi", "registered_at": "2026-11-01T10:00:00", "extra": {"loyalty_card": "X1"}},
        {"phone": "abc"}]}).json()
    assert r["accepted"] == 1 and r["rejected"][0]["index"] == 1

    r = pos.post("/api/v1/pos/invoices", json={"invoices": [INV]}).json()
    assert r == {"accepted": 1, "lines": 2, "rejected": []}
    # same invoice again -> replaced, not duplicated
    pos.post("/api/v1/pos/invoices", json={"invoices": [INV]})
    s = admin.get("/api/sales", params={"q": "01001112222"}).json()
    assert s["total"] == 2 and s["sales"] == 200.0  # 2*50 + (120-20)
    assert all(row["district"] == "Maadi" and row["branch"] == "POS Maadi" for row in s["rows"])

    # return -> negative, void -> removed
    ret = {**INV, "invoice_no": "M-1002", "status": "return", "lines": [{"item_code": "P1", "quantity": 1, "unit_price": 50}]}
    pos.post("/api/v1/pos/invoices", json={"invoices": [ret]})
    assert admin.get("/api/sales", params={"q": "01001112222"}).json()["sales"] == 150.0
    pos.post("/api/v1/pos/invoices", json={"invoices": [{**ret, "status": "void", "lines": []}]})
    assert admin.get("/api/sales", params={"q": "01001112222"}).json()["sales"] == 200.0

    st = pos.get("/api/v1/pos/sync-state").json()
    assert st["invoices"] == 1 and st["last_invoice_date"].startswith("2026-11-10T14:35")
    assert st["customers"] >= 1


def test_gzip_backfill_batch(pos, admin):
    invs = [{**INV, "invoice_no": f"H-{i}", "invoice_date": f"2025-0{1 + i % 9}-1{i % 9}T09:00:00"}
            for i in range(300)]
    body = gzip.compress(json.dumps({"invoices": invs}).encode())
    r = pos.post("/api/v1/pos/invoices", content=body,
                 headers={"Content-Encoding": "gzip", "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 300


def test_revoke(pos, admin):
    keys = admin.get("/api/integration/keys").json()
    admin.delete(f"/api/integration/keys/{keys[0]['id']}")
    assert pos.get("/api/v1/pos/ping").status_code == 401


def test_live_screen(admin):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app import main
    key = admin.post("/api/integration/keys", json={"name": "Live POS", "branch": "Live Branch"}).json()["key"]
    c = TestClient(main.app)
    c.headers["X-API-Key"] = key
    now = datetime.now(ZoneInfo("Africa/Cairo")).replace(tzinfo=None, microsecond=0).isoformat()
    c.post("/api/v1/pos/customers", json={"customers": [{"phone": "01005556666", "name": "Live Cust", "registered_at": now}]})
    c.post("/api/v1/pos/invoices", json={"invoices": [{**INV, "invoice_no": "L-1", "invoice_date": now,
                                                        "customer_phone": "01005556666"}]})
    r = admin.get("/api/live").json()
    assert r["kpis"]["invoices"] >= 1 and r["kpis"]["sales"] >= 200
    b = next(x for x in r["branches"] if x["branch"] == "Live Branch")
    assert b["state"] == "online" and b["invoices"] == 1
    assert r["feed"][0]["invoice_no"] == "L-1" and r["feed"][0]["cashier"] == "Mona"
    assert any(x["phone"] == "01005556666" for x in r["new_customers"])
    assert r["hourly"]
