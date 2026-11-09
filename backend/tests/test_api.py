import io
import time
import zipfile

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
        c.tmp = d
        yield c


def upload(client, data: bytes, filename: str, chunk=50_000):
    init = client.post("/api/imports/uploads", json={"filename": filename, "size": len(data)})
    assert init.status_code == 200, init.text
    uid = init.json()["upload_id"]
    for off in range(0, len(data), chunk):
        r = client.put(f"/api/imports/uploads/{uid}", params={"offset": off},
                       content=data[off:off + chunk])
        assert r.status_code == 200, r.text
    r = client.post(f"/api/imports/uploads/{uid}/finish")
    assert r.status_code == 200, r.text
    return r.json()


def _import(client, path, mode="replace_period", mapping_fix=None, filename="sales.xlsx"):
    up = upload(client, path.read_bytes() if hasattr(path, "read_bytes") else path, filename)
    mapping = up["mapping"]
    mapping.update(mapping_fix or {})
    imp = client.post("/api/imports/commit", json={
        "upload_id": up["upload_id"], "mapping": mapping, "mode": mode})
    assert imp.status_code == 200, imp.text
    for _ in range(300):
        st = client.get(f"/api/imports/{imp.json()['import_id']}").json()
        if st["status"] != "running":
            return up, st
        time.sleep(0.1)
    raise AssertionError("import timed out")


def test_login_required():
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/api/summary").status_code == 401
        assert c.get("/api/branding").status_code == 200  # public for the login page


def test_import_and_analytics(client):
    up, st = _import(client, client.sample, mapping_fix={"address": "Customer Address"})
    assert up["mapping"]["phone"] == "Mobile No"
    assert up["duplicate_of"] is None
    assert st["status"] == "done", st
    assert st["progress"] == 100
    assert st["rows_imported"] > 0 and st["invalid_dates"] == 0

    meta = client.get("/api/meta").json()
    assert set(meta["branches"]) <= {"Maadi", "Zamalek", "Nasr City", "Heliopolis"}
    assert "Maadi" in meta["districts"] or "Degla" in meta["districts"]

    s = client.get("/api/summary").json()
    assert s["kpis"]["customers"] == 80
    assert s["kpis"]["invoices"] > 80
    seg = s["segments"]
    assert seg["active"] + seg["attention"] + seg["inactive"] == 80

    # same file again: flagged as duplicate, and replace_period must not duplicate rows
    up2, st2 = _import(client, client.sample)
    assert up2["duplicate_of"] is not None
    assert st2["rows_replaced"] == st["rows_imported"]
    s2 = client.get("/api/summary").json()
    assert s2["kpis"]["total_sales"] == s["kpis"]["total_sales"]

    # append_new skips everything already loaded
    _, st3 = _import(client, client.sample, mode="append_new")
    assert st3["rows_imported"] == 0


def test_zip_and_csv_upload(client):
    from .sample_data import make_rows
    csv = make_rows(n_customers=5, seed=9).to_csv(index=False).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("export.csv", csv)
    up = upload(client, buf.getvalue(), "export.zip")
    assert up["mapping"]["phone"] == "Mobile No"
    assert up["sheets"] == []


def test_filters_and_lists(client):
    c = client.get("/api/customers", params={"page_size": 10}).json()
    assert c["total"] == 80 and len(c["rows"]) == 10
    first = c["rows"][0]
    assert first["phone"].startswith("01") and len(first["phone"]) == 11
    assert first["status"] in ("inactive", "attention", "active")
    assert first["segment"] and first["churn_risk"] and first["cid"]

    br = client.get("/api/customers", params={"branch": "Maadi"}).json()
    assert all(r["branch"] == "Maadi" for r in br["rows"])

    rng = client.get("/api/summary", params={"date_from": "2026-10-01",
                                             "date_to": "2026-10-31"}).json()
    full = client.get("/api/summary").json()
    assert rng["kpis"]["total_sales"] < full["kpis"]["total_sales"]
    assert rng["previous"] is not None and rng["new_customers"] is not None

    prof = client.get(f"/api/customers/{first['cid']}").json()
    assert prof["summary"]["phone"] == first["phone"] and prof["visits"]

    area = client.get("/api/area", params={"min_customers": 1}).json()
    assert area["districts"] and area["branch_district"]

    sales = client.get("/api/sales", params={"q": first["phone"]}).json()
    assert sales["total"] > 0

    for flag in ("due_soon", "overdue", "multi_branch", "high_value"):
        assert client.get("/api/customers", params={"flag": flag}).status_code == 200


def test_insights(client):
    ins = client.get("/api/insights").json()
    assert sum(r["customers"] for r in ins["rfm"]) == 80
    assert ins["cohorts"] and ins["heatmap"] and ins["new_vs_returning"]
    assert ins["pareto"]["top20_share"] > 20
    assert isinstance(ins["alerts"], list) and all("ar" in a for a in ins["alerts"])
    assert ins["basket"], "sample data has repeated item pairs"


def test_exports(client):
    for url, params in [("/api/summary", {}), ("/api/customers", {"view": "business"}),
                        ("/api/customers", {"view": "recommendations", "lang": "ar"}),
                        ("/api/area", {}), ("/api/sales", {"lang": "ar"}),
                        ("/api/insights", {"lang": "ar"}), ("/api/audit", {})]:
        r = client.get(url, params={**params, "export": "true"})
        assert r.status_code == 200, (url, r.text)
        assert r.content[:2] == b"PK"


def test_roles_masking_and_audit(client):
    # custom role: customers but no phones, no export
    r = client.post("/api/roles", json={"name": "callcenter", "description": "test",
                                        "permissions": ["dashboard", "customers"]})
    assert r.status_code == 200, r.text
    r = client.post("/api/users", json={"username": "maadi_mgr", "password": "manager-pass",
                                        "role": "callcenter", "branches": ["Maadi"]})
    assert r.status_code == 200, r.text

    from app.main import app
    m = TestClient(app)
    tok = m.post("/api/auth/login", json={"username": "maadi_mgr",
                                          "password": "manager-pass"}).json()["token"]
    m.headers["Authorization"] = f"Bearer {tok}"
    assert m.get("/api/meta").json()["branches"] == ["Maadi"]
    rows = m.get("/api/customers").json()["rows"]
    assert rows and all("****" in r["phone"] for r in rows)
    assert m.get("/api/customers", params={"branch": "Zamalek"}).json()["rows"] == []
    assert m.get("/api/customers", params={"export": "true"}).status_code == 403
    assert m.get("/api/imports").status_code == 403
    assert m.get("/api/area").status_code == 403
    assert m.get("/api/customers", params={"view": "business"}).status_code == 403

    log = client.get("/api/audit").json()
    actions = {r["action"] for r in log["rows"]}
    assert {"login", "user_create", "role_create", "import_start", "export"} <= actions


def test_ai_without_key(client):
    r = client.post("/api/ai/ask", json={"question": "How are sales?"})
    assert r.status_code == 400 and "key" in r.json()["detail"]


def test_ai_with_mocked_openai(client, monkeypatch):
    import httpx
    sent = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"model": "test", "choices": [{"message": {"content": "All good"}}]}

    def fake_post(url, **kw):
        sent.update(kw["json"])
        return Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    s = client.get("/api/settings").json()
    s.update(openai_api_key="sk-test-1234")
    for k in ("openai_key_set", "openai_key_hint", "app_name", "primary_color"):
        s.pop(k, None)
    assert client.put("/api/settings", json=s).status_code == 200
    assert client.get("/api/settings").json()["openai_key_hint"] == "...1234"
    r = client.post("/api/ai/ask", json={"question": "How are sales?", "lang": "ar"})
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "All good"
    data_msg = sent["messages"][1]["content"]
    first_phone = client.get("/api/customers").json()["rows"][0]["phone"]
    assert first_phone not in data_msg  # no personal data sent to OpenAI


def test_branding_logo(client):
    png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00"
           b"\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
           b"\x00\x00\x00\x00IEND\xaeB`\x82")
    r = client.post("/api/branding/logo", files={"file": ("logo.png", png, "image/png")})
    assert r.status_code == 200 and r.json()["logo_url"]
    assert client.get("/api/branding/logo").content == png
    r = client.put("/api/branding", json={"app_name": "Lotus Pharmacies",
                                          "primary_color": "#0d47a1"})
    assert r.json()["app_name"] == "Lotus Pharmacies"
    assert client.post("/api/branding/logo",
                       files={"file": ("x.svg", b"<svg/>", "image/svg+xml")}).status_code == 400
