from app.core.address import extract_district
from app.core.columns import find_columns
from app.core.phone import normalize_egy_phone


def test_phone_normalisation():
    assert normalize_egy_phone("01033316088") == "01033316088"
    assert normalize_egy_phone(1033316088) == "01033316088"
    assert normalize_egy_phone("1033316088.0") == "01033316088"
    assert normalize_egy_phone("+20 103 331 6088") == "01033316088"
    assert normalize_egy_phone("201033316088") == "01033316088"
    assert normalize_egy_phone(None) == ""
    assert normalize_egy_phone("nan") == ""


def test_column_mapping_no_double_assignment():
    cols = ["Mobile No", "Customer Name", "Branch Name", "Location", "Posting Date",
            "Sales Type_name", "Material", "Material Description", "Material Group",
            "Qty", "Net Amount"]
    m = find_columns(cols)
    assert m["phone"] == "Mobile No"
    assert m["name"] == "Customer Name"
    assert m["branch"] == "Branch Name"
    assert m["invoice_date"] == "Posting Date"
    assert m["invoice_type"] == "Sales Type_name"
    assert m["item_code"] == "Material"
    assert m["item_name"] == "Material Description"
    assert m["material_group"] == "Material Group"
    assert m["quantity"] == "Qty"
    assert m["item_price"] == "Net Amount"
    used = [v for v in m.values() if v]
    assert len(used) == len(set(used))


def test_arabic_headers():
    m = find_columns(["رقم الموبايل", "اسم العميل", "الفرع", "التاريخ", "القيمة"])
    assert m["phone"] == "رقم الموبايل"
    assert m["name"] == "اسم العميل"
    assert m["branch"] == "الفرع"
    assert m["invoice_date"] == "التاريخ"
    assert m["item_price"] == "القيمة"


def test_district():
    assert extract_district("12 Street, Maadi district, Cairo") == "Maadi"
    assert extract_district("Building 5, Zamalek") == "Zamalek"
    assert extract_district(None) == "Unknown"


def test_date_parsing():
    from datetime import datetime

    import pandas as pd

    from app.core.importer import _parse_dates
    s = pd.Series([datetime(2026, 10, 12, 14), "2026-10-12", "12/10/2026", 46307, None, "bad"],
                  dtype=object)
    out = _parse_dates(s).dt.strftime("%Y-%m-%d").tolist()
    assert out[:4] == ["2026-10-12"] * 4
    assert pd.isna(out[4]) and pd.isna(out[5])
