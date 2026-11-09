import time

import pytest
from fastapi.testclient import TestClient

from .sample_data import write_sample


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from app import main
    d = tmp_path_factory.mktemp("data")
    with TestClient(main.app) as c:
        r = c.post("/api/auth/login", json={"username": "admin", "password": "admin-pass-123"})
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        c.sample = write_sample(d / "sample.xlsx", n_customers=80)
        yield c


def _import(client, path, mode="replace_period", mapping_fix=None):
    with open(path, "rb") as fh:
        up = client.post("/api/imports/upload", files={"file": ("sales.xlsx", fh)}).json()
    mapping = up["mapping"]
    mapping.update(mapping_fix or {})
    imp = client.post("/api/imports/commit", json={
        "upload_id": up["upload_id"], "mapping": mapping, "mode": mode}).json()
    for _ in range(100):
        st = client.get(f"/api/imports/{imp['import_id']}").json()
        if st["status"] != "running":
            return up, st
        time.sleep(0.1)
    raise AssertionError("import timed out")


def test_login_required():
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/api/summary").status_code == 401


def test_import_and_analytics(client):
    up, st = _import(client, client.sample, mapping_fix={"address": "Customer Address"})
    assert up["mapping"]["phone"] == "Mobile No"
    assert st["status"] == "done", st
    assert st["rows_imported"] > 0 and st["invalid_dates"] == 0

    meta = client.get("/api/meta").json()
    assert set(meta["branches"]) <= {"Maadi", "Zamalek", "Nasr City", "Heliopolis"}
    assert "Maadi" in meta["districts"] or "Degla" in meta["districts"]

    s = client.get("/api/summary").json()
    assert s["kpis"]["customers"] == 80
    assert s["kpis"]["invoices"] > 80
    seg = s["segments"]
    assert seg["active"] + seg["attention"] + seg["inactive"] == 80

    # re-importing the same file with replace_period must not duplicate rows
    _, st2 = _import(client, client.sample)
    assert st2["rows_replaced"] == st["rows_imported"]
    s2 = client.get("/api/summary").json()
    assert s2["kpis"]["total_sales"] == s["kpis"]["total_sales"]

    # append_new skips everything already loaded
    _, st3 = _import(client, client.sample, mode="append_new")
    assert st3["rows_imported"] == 0


def test_filters_and_lists(client):
    c = client.get("/api/customers", params={"page_size": 10}).json()
    assert c["total"] == 80 and len(c["rows"]) == 10
    first = c["rows"][0]
    assert first["phone"].startswith("01") and len(first["phone"]) == 11
    assert first["status"] in ("inactive", "attention", "active")

    br = client.get("/api/customers", params={"branch": "Maadi"}).json()
    assert all(r["branch"] == "Maadi" for r in br["rows"])

    rng = client.get("/api/summary", params={"date_from": "2026-10-01",
                                             "date_to": "2026-10-31"}).json()
    full = client.get("/api/summary").json()
    assert rng["kpis"]["total_sales"] < full["kpis"]["total_sales"]
    assert rng["previous"] is not None and rng["new_customers"] is not None

    prof = client.get(f"/api/customers/{first['phone']}").json()
    assert prof["summary"]["phone"] == first["phone"] and prof["visits"]

    area = client.get("/api/area", params={"min_customers": 1}).json()
    assert area["districts"] and area["branch_district"]

    sales = client.get("/api/sales", params={"q": first["phone"]}).json()
    assert sales["total"] > 0


def test_exports(client):
    for url, params in [("/api/summary", {}), ("/api/customers", {"view": "business"}),
                        ("/api/customers", {"view": "recommendations", "lang": "ar"}),
                        ("/api/area", {}), ("/api/sales", {"lang": "ar"})]:
        r = client.get(url, params={**params, "export": "true"})
        assert r.status_code == 200, (url, r.text)
        assert r.content[:2] == b"PK"


def test_branch_restricted_manager(client):
    r = client.post("/api/users", json={"username": "maadi_mgr", "password": "manager-pass",
                                        "branches": ["Maadi"]})
    assert r.status_code == 200
    from fastapi.testclient import TestClient as TC
    from app.main import app
    m = TC(app)
    tok = m.post("/api/auth/login", json={"username": "maadi_mgr",
                                          "password": "manager-pass"}).json()["token"]
    m.headers["Authorization"] = f"Bearer {tok}"
    assert m.get("/api/meta").json()["branches"] == ["Maadi"]
    rows = m.get("/api/customers", params={"branch": "Zamalek"}).json()["rows"]
    assert rows == []
    assert m.get("/api/imports").status_code == 403
