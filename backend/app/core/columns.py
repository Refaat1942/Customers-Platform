"""Smart column mapper (ported from legacy/column_mapper.py).

Changes from the desktop version:
  * a source column can only be assigned to ONE field (no more branch/address
    both pointing at "location", or category/material group sharing a column);
  * a few Arabic header names and two optional fields (invoice_no, district);
  * the web UI shows this guess to the user, who confirms or corrects it.
"""

import re
from difflib import get_close_matches

# order matters: earlier fields win ties
FIELDS = [
    "phone",
    "invoice_date",
    "item_price",
    "branch",
    "name",
    "address",
    "district",
    "invoice_no",
    "invoice_type",
    "item_name",
    "item_code",
    "material_group",
    "item_category",
    "quantity",
    "item_unit",
]

REQUIRED_FIELDS = ["phone", "invoice_date", "item_price"]

KEYWORDS = {
    "phone": [
        "phone", "mobile", "tel", "telephone", "customer phone", "client phone",
        "mobile no", "mobile_no", "phone number", "phonenumber", "mobilephone",
        "تليفون", "موبايل", "رقم الهاتف", "الهاتف", "رقم الموبايل",
    ],
    "branch": [
        "branch", "branch id", "branchid", "branch_code", "branch code", "store",
        "pharmacy", "branch name", "branch_name", "site", "plant", "الفرع", "فرع",
    ],
    "name": [
        "name", "customer name", "client name", "consumername", "fullname",
        "full name", "اسم العميل", "الاسم", "العميل",
    ],
    "address": [
        "address", "customer address", "addr", "location", "street", "عنوان", "العنوان",
    ],
    "district": [
        "district", "area", "zone", "region", "neighborhood", "المنطقة", "منطقة", "الحي",
    ],
    "invoice_no": [
        "invoice no", "invoice number", "invoice_no", "invoice id", "receipt no",
        "receipt number", "bill no", "bill number", "transaction id", "document no",
        "رقم الفاتورة",
    ],
    "invoice_date": [
        "date", "invoice date", "receipt date", "invdate", "transactiondate",
        "receiptdate", "datetime", "post date", "posting date", "التاريخ", "تاريخ",
    ],
    "invoice_type": [
        "type", "invoice type", "sales type", "sales type name", "sales type_name",
        "salestype", "sale type", "txn type", "transaction type", "نوع البيع",
    ],
    "item_code": [
        "item", "item code", "itemcode", "sku", "product code", "material",
        "material number", "material no", "material code", "barcode", "code",
        "كود الصنف",
    ],
    "item_name": [
        "item name", "product", "product name", "material name",
        "material description", "description", "desc", "اسم الصنف", "الصنف",
    ],
    "material_group": [
        "material group", "mg", "item group", "product group", "category group",
    ],
    "item_category": [
        "category", "item category", "itemcategory", "cat", "product category",
        "material category", "merchandise category", "group", "الفئة",
    ],
    "quantity": [
        "qty", "quantity", "units", "qnt", "sales qty", "amount_qty", "الكمية",
    ],
    "item_unit": ["unit", "uom", "measure", "unit measure", "bun", "الوحدة"],
    "item_price": [
        "price", "unit price", "item price", "total", "total price", "amount",
        "amt", "net", "net amount", "value", "sales", "revenue", "price egp",
        "price_egp", "rsp", "retail", "السعر", "القيمة", "الاجمالي", "الإجمالي",
    ],
}

NBSP = " "


def clean_col_name(s) -> str:
    if s is None:
        return ""
    s = str(s).replace(NBSP, " ").replace("_", " ")
    s = re.sub(r"[^\w\s؀-ۿ]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def _variants(keywords):
    out = []
    for kw in keywords:
        c = clean_col_name(kw)
        for v in (c, c.replace(" ", "")):
            if v and v not in out:
                out.append(v)
    return out


VARIANTS = {k: _variants(v) for k, v in KEYWORDS.items()}


def find_columns(columns, fuzzy=True, fuzzy_cutoff=0.78) -> dict:
    """Return {field: source column name or None}."""
    cleaned_map = {}
    for c in columns:
        cleaned_map.setdefault(clean_col_name(c), c)

    mapped = {k: None for k in FIELDS}
    used = set()

    def assign(field, orig):
        mapped[field] = orig
        used.add(orig)

    # 1) exact match on cleaned names
    for field in FIELDS:
        for var in VARIANTS[field]:
            orig = cleaned_map.get(var)
            if orig is not None and orig not in used:
                assign(field, orig)
                break

    # 2) substring match (keywords of 3+ chars, avoids "cat" in "location")
    for field in FIELDS:
        if mapped[field]:
            continue
        for cleaned, orig in cleaned_map.items():
            if orig in used:
                continue
            if any(len(v) >= 4 and v in cleaned for v in VARIANTS[field]):
                assign(field, orig)
                break

    # 3) fuzzy match for typos
    if fuzzy:
        for field in FIELDS:
            if mapped[field]:
                continue
            free = [c for c, o in cleaned_map.items() if o not in used]
            for var in VARIANTS[field]:
                if len(var) < 4:
                    continue
                m = get_close_matches(var, free, n=1, cutoff=fuzzy_cutoff)
                if m:
                    assign(field, cleaned_map[m[0]])
                    break

    return mapped
