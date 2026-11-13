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


def _commit_and_wait(client, up, kind, mode, mapping=None):
    imp = client.post("/api/imports/commit", json={
        "upload_id": up["upload_id"], "kind": kind, "mapping": mapping or up["mappings"][kind],
        "mode": mode})
    assert imp.status_code == 200, imp.text
    for _ in range(300):
        st = client.get(f"/api/imports/{imp.json()['import_id']}").json()
        if st["status"] != "running":
            return st
        time.sleep(0.1)
    raise AssertionError("import timed out")


def test_customer_list_detected_and_linked(client):
    import pandas as pd
    first = client.get("/api/customers", params={"page_size": 2}).json()["rows"]
    rows = [{"Phone Number": r["phone"][1:], "Frist Name": "أحمد", "Last Name": f"Test{i}",
             "Region": "Cairo", "City": "New Cairo", "District": "Fifth Settlement",
             "Area": "Area 5", "Street Name": "90 St", "Building": "12", "Floor": "3",
             "Flat Number": "7", "Landmark": "", "Full Address": "Cairo, New Cairo, 90 St"}
            for i, r in enumerate(first)]
    rows.append({**rows[0], "Phone Number": "1099999999", "Last Name": "NoSales"})
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    up = upload(client, buf.getvalue(), "RMS Customer.xlsx")
    assert up["kind"] == "customers", up["kind_reason"]
    m = up["mappings"]["customers"]
    assert m["phone"] == "Phone Number" and m["first_name"] == "Frist Name"
    assert m["address"] == "Full Address" and m["district"] == "District"
    st = _commit_and_wait(client, up, "customers", "upsert")
    assert st["status"] == "done", st
    assert st["rows_imported"] == 3

    prof = client.get(f"/api/customers/{first[0]['cid']}").json()
    assert prof["directory"]["city"] == "New Cairo"
    assert prof["summary"]["district"] == "Fifth Settlement"  # sales enriched from the list
    ins = client.get("/api/insights").json()
    assert ins["directory"]["listed"] == 3 and ins["directory"]["never_bought"] == 1


def test_sales_detected_from_values_with_odd_headers(client):
    import pandas as pd
    from datetime import datetime
    df = pd.DataFrame({"Col A": ["01012345678", "01198765432"] * 10,
                       "Col B": [datetime(2026, 1, d + 1) for d in range(20)],
                       "Col C": [125.5, 99.75] * 10, "Col D": ["x", "y"] * 10})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    up = upload(client, buf.getvalue(), "odd.xlsx")
    assert up["kind"] == "sales"
    m = up["mapping"]
    assert (m["phone"], m["invoice_date"], m["item_price"]) == ("Col A", "Col B", "Col C")


def test_customer_invoice_stats_and_products(client):
    r = client.get("/api/customers", params={"page_size": 5, "sort": "max_invoice"}).json()["rows"]
    assert r and all(x["max_invoice"] >= x["min_invoice"] for x in r)
    assert r[0]["items_count"] >= 1 and r[0]["fav_item"]
    p = client.get("/api/products").json()
    assert p["total"] >= 5 and p["rows"][0]["sales"] >= p["rows"][-1]["sales"]
    assert p["rows"][0]["customers"] >= p["rows"][0]["repeat_buyers"]
    assert client.get("/api/products", params={"export": "true", "lang": "ar"}).content[:2] == b"PK"


def test_multi_sheet_workbook(client):
    import pandas as pd
    from .sample_data import make_rows
    sales = make_rows(n_customers=6, seed=21)
    cust = pd.DataFrame({"Mobile": sales["Mobile No"].unique()[:4], "Full Name": ["A", "B", "C", "D"],
                         "City": ["Giza"] * 4, "District": ["Dokki"] * 4})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as xw:
        sales.to_excel(xw, sheet_name="Sales", index=False)
        cust.to_excel(xw, sheet_name="Customers", index=False)
        pd.DataFrame().to_excel(xw, sheet_name="Empty", index=False)
    up = upload(client, buf.getvalue(), "book.xlsx")
    kinds = {s["sheet"]: s["kind"] for s in up["sheets_info"]}
    assert kinds == {"Sales": "sales", "Customers": "customers", "Empty": "empty"}
    jobs = [{"sheet": s["sheet"], "kind": s["kind"], "mapping": s["mapping"],
             "mode": "replace_period" if s["kind"] == "sales" else "upsert"}
            for s in up["sheets_info"] if s["kind"] in ("sales", "customers")]
    r = client.post("/api/imports/commit", json={"upload_id": up["upload_id"], "jobs": jobs})
    assert r.status_code == 200, r.text
    ids = r.json()["import_ids"]
    for _ in range(300):
        st = [client.get(f"/api/imports/{i}").json() for i in ids]
        if all(x["status"] != "running" for x in st):
            break
        time.sleep(0.1)
    assert all(x["status"] == "done" for x in st), st
    assert {x["kind"] for x in st} == {"sales", "customers"}


def test_merge_mode_skips_duplicates_and_deletes_nothing(client):
    before = client.get("/api/sales", params={"page_size": 1}).json()["total"]
    _, st = _import(client, client.sample, mode="merge")
    assert st["status"] == "done" and st["rows_replaced"] == 0
    after = client.get("/api/sales", params={"page_size": 1}).json()["total"]
    assert after >= before  # nothing deleted; already-loaded lines skipped
    assert st["rows_skipped"] > 0


def test_two_files_imported_together(client):
    from .sample_data import make_rows
    ups = []
    for seed in (31, 32):
        buf = io.BytesIO()
        make_rows(n_customers=4, seed=seed).to_excel(buf, index=False)
        ups.append(upload(client, buf.getvalue(), f"file{seed}.xlsx"))
    ids = []
    for up in ups:
        s = up["sheets_info"][0]
        r = client.post("/api/imports/commit", json={"upload_id": up["upload_id"], "jobs": [
            {"sheet": s["sheet"], "kind": s["kind"], "mapping": s["mapping"], "mode": "merge"}]})
        assert r.status_code == 200, r.text
        ids += r.json()["import_ids"]
    for _ in range(300):
        st = [client.get(f"/api/imports/{i}").json() for i in ids]
        if all(x["status"] != "running" for x in st):
            break
        time.sleep(0.1)
    assert [x["status"] for x in st] == ["done", "done"], st
    assert all(x["rows_imported"] > 0 for x in st)


def test_directory_page(client):
    s = client.get("/api/directory/summary").json()
    assert s["kpis"]["total"] >= 3 and s["by_city"]
    assert s["kpis"]["bought"] + s["kpis"]["never_bought"] == s["kpis"]["total"]
    lst = client.get("/api/directory", params={"bought": "false"}).json()
    assert lst["total"] >= 1 and all(not r["bought"] for r in lst["rows"])
    assert lst["filters"]["city"]
    assert client.get("/api/directory", params={"export": "true"}).content[:2] == b"PK"


def test_sales_rows_with_empty_phone(client):
    import pandas as pd
    from datetime import datetime
    df = pd.DataFrame({"Mobile": ["01012345678", None, "", "01198765432"],
                       "Date": [datetime(2025, 3, 1)] * 4, "Net Amount": [10.5, 20.0, 30.0, 40.25]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    up = upload(client, buf.getvalue(), "Car 2024 All.xlsx")
    st = _commit_and_wait(client, up, "sales", "merge", up["mappings"]["sales"])
    assert st["status"] == "done", st
    assert st["rows_imported"] == 4  # rows without a phone still count in total sales


def test_duplicates_across_different_reports(client):
    """Same sales from two differently-shaped reports must not be counted twice."""
    import pandas as pd
    from datetime import datetime
    a = pd.DataFrame({"Mobile": ["01055500001", "01055500001", "01055500002"],
                      "Invoice No": ["X1", "X1", "X2"],
                      "Posting Date": [datetime(2024, 5, 1, 13, 30)] * 2 + [datetime(2024, 5, 2, 9, 0)],
                      "Material": ["A1", "B1", "A1"], "Material Description": ["Aspirin", "Bandage", "Aspirin"],
                      "Qty": [1, 2, 1], "Net Amount": [25.0, 40.0, 25.0]})
    # other report: no invoice number, date only, product name only, no quantity
    b = pd.DataFrame({"Phone": ["1055500001", "1055500001", "1055500002", "01055500003"],
                      "Date": ["01/05/2024", "01/05/2024", "02/05/2024", "03/05/2024"],
                      "Item Name": ["Aspirin", "Bandage", "Aspirin", "Aspirin"],
                      "Value": [25.0, 40.0, 25.0, 25.0]})
    ids = []
    for df, name in ((a, "report_a.xlsx"), (b, "report_b.xlsx")):
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        up = upload(client, buf.getvalue(), name)
        st = _commit_and_wait(client, up, "sales", "merge", up["mappings"]["sales"])
        assert st["status"] == "done", st
        ids.append(st)
    assert ids[0]["rows_imported"] == 3
    assert ids[1]["rows_imported"] == 1 and ids[1]["rows_skipped"] == 3  # only the new 03/05 sale
    total = client.get("/api/sales", params={"q": "010555000"}).json()
    assert total["total"] == 4 and total["sales"] == 115.0


def test_find_and_remove_stored_duplicates(client):
    _import(client, client.sample, mode="replace_period")      # baseline
    before = client.get("/api/sales", params={"page_size": 1}).json()["total"]
    # force the same file in again WITHOUT de-duplication (append via replace_all of nothing)
    from app import db
    cur = db.cursor()
    cur.execute("INSERT INTO sales SELECT * FROM sales WHERE import_id = (SELECT max(import_id) FROM sales)")
    cur.execute("UPDATE sales SET import_id = 99999 WHERE ctid IN (SELECT ctid FROM sales WHERE import_id = "
                "(SELECT max(import_id) FROM sales WHERE import_id < 99999) LIMIT 50)")
    dup = client.get("/api/maintenance/duplicates").json()
    assert dup["duplicate_lines"] > 0
    r = client.delete("/api/maintenance/duplicates").json()
    assert r["removed"] == dup["duplicate_lines"]
    assert client.get("/api/maintenance/duplicates").json()["duplicate_lines"] == 0


def test_queued_import_can_be_cancelled(client):
    from app.core import importer
    importer._import_lock.acquire()  # pretend another big import is running
    try:
        up = upload(client, client.sample.read_bytes(), "queued.xlsx")
        s = up["sheets_info"][0]
        iid = client.post("/api/imports/commit", json={"upload_id": up["upload_id"], "jobs": [
            {"sheet": s["sheet"], "kind": "sales", "mapping": s["mapping"], "mode": "merge"}]}).json()["import_id"]
        assert client.get(f"/api/imports/{iid}").json()["stage"] == "queued"
        assert client.post(f"/api/imports/{iid}/cancel").status_code == 200
    finally:
        importer._import_lock.release()
    for _ in range(100):
        st = client.get(f"/api/imports/{iid}").json()
        if st["status"] != "running":
            break
        time.sleep(0.1)
    assert st["status"] == "failed" and st["message"] == "Cancelled by user" and st["rows_imported"] == 0


def test_customer_totals_and_data_check(client):
    t = client.get("/api/customer-totals", params={"date_from": "2026-01-01"}).json()
    assert t["totals"]["customers"] > 0 and t["by_type"]
    assert abs(sum(x["sales"] for x in t["by_type"]) - t["totals"]["sales"]) < 1
    full = client.get("/api/customer-totals").json()["totals"]
    d = client.get("/api/maintenance/data-check").json()
    assert d["totals"]["lines"] == full["lines"] and d["totals"]["sales"] == full["sales"]
    ok = [i for i in d["imports"] if i["kind"] == "sales" and i["status"] == "done" and i["rows_now"]]
    assert ok and all(i["rows_now"] > 0 for i in ok)
    assert client.post("/api/maintenance/refresh").json()["ok"]


def test_separate_date_and_time_columns_and_branch_invoices(client):
    import pandas as pd
    df = pd.DataFrame({"Posting Date": ["20250127", "20250127", "20250128", "20250128"],
                       "Time": ["14:35:00", "14:35:00", "09:10:00", "09:10:00"],
                       "Customer Phone": ["01077700001", "01077700001", "01077700002", "01077700003"],
                       "Branch": ["Maadi", "Maadi", "Maadi", "Nasr City"],
                       "Bill No": ["1001", "1001", "1002", "1002"],          # same number, 2 branches
                       "Material Description": ["A", "B", "A", "A"], "Net Amount": [10.0, 20.0, 30.0, 40.0]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    up = upload(client, buf.getvalue(), "pos_export.xlsx")
    m = up["mappings"]["sales"]
    assert m["invoice_date"] == "Posting Date" and m["invoice_time"] == "Time"
    st = _commit_and_wait(client, up, "sales", "merge", m)
    assert st["status"] == "done" and st["rows_imported"] == 4 and st["invalid_dates"] == 0
    rows = client.get("/api/sales", params={"q": "01077700001"}).json()["rows"]
    assert {r["invoice_date"] for r in rows} == {"2025-01-27T14:35:00"}
    c2 = client.get("/api/customers", params={"q": "01077700002"}).json()["rows"][0]
    c3 = client.get("/api/customers", params={"q": "01077700003"}).json()["rows"][0]
    assert c2["visits"] == 1 and c3["visits"] == 1
    inv = client.get("/api/customer-totals", params={"date_from": "2025-01-28", "date_to": "2025-01-28"}).json()
    assert inv["totals"]["invoices"] == 2   # 1002 in Maadi and 1002 in Nasr City are different


def test_summary_report_warning(client):
    import pandas as pd
    from datetime import datetime
    df = pd.DataFrame({"Phone": [f"0101234{i:04d}" for i in range(30)],
                       "Report Date": [datetime(2026, 1, 31)] * 30, "Total Sales": [100.5 + i for i in range(30)]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    up = upload(client, buf.getvalue(), "Customer Sales Report.xlsx")
    assert {"summary", "one_date"} <= set(up["sheets_info"][0]["warnings"])


def test_users_pos_export_rows_and_date_order(client):
    import pandas as pd
    rows = [["CA28", "53558", "ا مجدي", "01222125888", "Nasr City", "Delivery", "04/05/2026 0:00", "09:00:00 PM",
             "2000332", "MUSTELA SKIN FRESHENER 200ML", "PAK", 1, 615, "CI"],
            ["CA28", "53558", "ا مجدي", "01222125888", "Nasr City", "Delivery", "04/05/2026 0:00", "09:00:00 PM",
             "2009125", "FLAMINGO FACIAL&BODY SHAVERS 3PCS", "EA", 1, 280, "CL"],
            ["CA28", "53558", "ا مجدي", "01222125888", "Nasr City", "Delivery", "04/05/2026 0:00", "09:00:00 PM",
             "530", "DELIVERY FEES", "EA", 1, 30, "SERV"]]
    df = pd.DataFrame(rows, columns=["Site", "Doc No", "Customer", "Phone Number", "Customer Address", "Sales Type",
                                     "Posting Date", "Posting Time", "Material", "Material Description", "BUn",
                                     "Quantity", "Net Amount", "Material Group"])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    up = upload(client, buf.getvalue(), "pos_lines.xlsx")
    sh = up["sheets_info"][0]
    assert sh["text_dates"] and sh["date_order_sure"] is False  # 04/05 could be 4 May or 5 April
    m = sh["mappings"]["sales"]
    assert m["invoice_no"] == "Doc No" and m["invoice_time"] == "Posting Time"
    r = client.post("/api/imports/commit", json={"upload_id": up["upload_id"], "jobs": [
        {"sheet": sh["sheet"], "kind": "sales", "mapping": m, "mode": "merge", "date_order": "mdy"}]})
    iid = r.json()["import_id"]
    for _ in range(100):
        st = client.get(f"/api/imports/{iid}").json()
        if st["status"] != "running":
            break
        time.sleep(0.1)
    assert st["status"] == "done" and st["rows_imported"] == 3
    c = client.get("/api/customers", params={"q": "01222125888"}).json()["rows"][0]
    assert c["visits"] == 1 and c["total_spent"] == 925.0 and c["branch"] == "CA28"
    assert str(c["last_visit"]) == "2026-04-05"   # month/day/year chosen -> 5 April
    lines = client.get("/api/sales", params={"q": "01222125888"}).json()["rows"]
    assert {x["invoice_date"] for x in lines} == {"2026-04-05T21:00:00"}


def test_bad_remembered_mapping_is_corrected(client):
    """A layout remembered with the TIME column as date (old bug) must not be reused blindly."""
    import json

    import pandas as pd
    from app import db
    from app.core import importer
    from datetime import datetime
    df = pd.DataFrame({"Phone": ["01033300001"] * 60, "Date": [datetime(2026, 5, 4)] * 60,
                       "Time": ["09:00:00 PM"] * 60, "Item": ["A"] * 60, "Amount": [10.5] * 60})
    cols = list(df.columns)
    bad = {f: None for f in importer.FIELDS}
    bad.update(phone="Phone", invoice_date="Time", item_price="Amount", item_name="Item")
    db.cursor().execute("INSERT INTO saved_mappings VALUES (?, ?) ON CONFLICT (signature) DO UPDATE "
                        "SET mapping = EXCLUDED.mapping", [importer.header_signature(cols, "sales"), json.dumps(bad)])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    up = upload(client, buf.getvalue(), "again.xlsx")
    m = up["mappings"]["sales"]
    assert m["invoice_date"] == "Date" and m["invoice_time"] == "Time"

    # and if someone still picks the time column as the date, the import stops with a clear message
    st = _commit_and_wait(client, up, "sales", "merge", {**m, "invoice_date": "Time", "invoice_time": None})
    assert st["status"] == "failed" and "does not contain dates" in st["message"]


def test_customer_visit_items_and_data(client):
    c = client.get("/api/customers", params={"q": "01222125888"}).json()["rows"][0]
    prof = client.get(f"/api/customers/{c['cid']}").json()
    assert prof["items"] and prof["sales_info"]["branches"] == ["CA28"]
    v = prof["visits"][0]
    assert v["invoice_no"] == "53558"
    lines = client.get(f"/api/customers/{c['cid']}/visit", params={"key": v["visit_key"]}).json()["lines"]
    assert {x["item_name"] for x in lines} == {"MUSTELA SKIN FRESHENER 200ML", "FLAMINGO FACIAL&BODY SHAVERS 3PCS", "DELIVERY FEES"}
    assert sum(x["item_price"] for x in lines) == 925
    r = client.get(f"/api/customers/{c['cid']}", params={"export": "true"})
    assert r.status_code == 200 and r.content[:2] == b"PK"
