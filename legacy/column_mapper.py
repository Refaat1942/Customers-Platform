"""
Smart Column Mapper (robust + fuzzy)
يحدد الأعمدة مهما اختلفت أسمائها أو كانت فيها أخطاء بسيطة
"""

import re
from difflib import get_close_matches

# ---------- canonical keys used by app ----------
CANONICAL = [
    "phone",
    "branch",
    "name",
    "address",
    "invoice_date",
    "invoice_type",
    "item_code",
    "item_name",
    "material_group",
    "item_category",
    "quantity",
    "item_unit",
    "item_price",
]

# -------------------------------------------------------
#  🔥 EXPANDED KEYWORDS (Supports all your expected columns)
# -------------------------------------------------------
KEYWORDS = {
    "phone": [
        "phone", "mobile", "tel", "telephone", "customer phone",
        "client phone", "mobile no", "mobile_no", "phone number",
        "phonenumber", "mobilephone"
    ],

    "branch": [
        "branch", "branch id", "branchid", "branch_code", "branch code",
        "store", "location", "pharmacy", "branch name", "branch_name"
    ],

    "name": [
        "name", "customer name", "client name",
        "consumername", "fullname", "full name"
    ],

    "address": [
        "address", "customer address", "addr", "location",
        "site", "street", "عنوان", "العنوان"
    ],

    "invoice_date": [
        "date", "invoice date", "receipt date", "invdate",
        "transactiondate", "receiptdate", "datetime", "post. date"
    ],

    # --- Supports "Sales Type_name" exactly like your sheet ---
    "invoice_type": [
        "type", "invoice type", "sales type", "sales type name",
        "sales type_name", "salestype", "sale type", "txn type",
        "transaction type"
    ],

    # --- Supports Material / Material Number / Item Code ---
    "item_code": [
        "item", "item code", "itemcode", "sku", "product code",
        "material", "material number", "material no",
        "material code", "barcode", "code"
    ],

    # --- Supports Material Name / Description ---
    "item_name": [
        "item name", "product", "product name",
        "material name", "material description",
        "description", "desc"
    ],

    # --- Supports Material Group / Merchandise Category ---
    "material_group": [
        "material group", "group", "mg", "item group",
        "product group", "category group"
    ],

    # --- Item Category variations ---
    "item_category": [
        "category", "item category", "itemcategory", "cat",
        "product category", "material category", "group",
        "item group", "material group", "merchandise category",
        "product group"
    ],

    "quantity": [
        "qty", "quantity", "units", "qnt", "sales qty", "amount_qty"
    ],

    "item_unit": [
        "unit", "uom", "measure", "unit measure", "bun"
    ],

    # --- Supports RSP / Retail price ---
    "item_price": [
        "price", "unit price", "item price", "total", "total price",
        "amount", "amt", "net", "net amount", "value",
        "sales", "revenue", "price egp", "price_egp",
        "rsp", "retail"
    ]
}

# ---------- utility helpers ----------
NBSP = "\u00A0"

def clean_col_name(s: str) -> str:
    """Normalize column name -> small, cleaned, spaced"""
    if s is None:
        return ""
    s = str(s)
    s = s.replace(NBSP, " ")
    s = s.replace("_", " ")
    s = re.sub(r"[^\w\s\u0600-\u06FF]", " ", s)  # remove symbols but keep Arabic
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()

def variants_from_keywords(keywords):
    """Generate multiple patterns for each keyword"""
    out = set()
    for kw in keywords:
        cleaned = clean_col_name(kw)
        out.add(cleaned)
        out.add(cleaned.replace(" ", ""))     # e.g. "material name" → "materialname"
    return list(out)

VARIANTS = {k: variants_from_keywords(v) for k, v in KEYWORDS.items()}

# ---------- main function ----------
def find_columns(columns, fuzzy=True, fuzzy_cutoff=0.78):
    cleaned_map = {clean_col_name(c): c for c in columns}

    mapped = {k: None for k in CANONICAL}

    # ----------------------------------------------------
    # 1) exact cleaned keyword match
    # ----------------------------------------------------
    for canon in CANONICAL:
        for var in VARIANTS.get(canon, []):
            if var in cleaned_map:
                mapped[canon] = cleaned_map[var]
                break
        if mapped[canon]:
            continue

    # ----------------------------------------------------
    # 2) substring matching (strong signal)
    # ----------------------------------------------------
    for cleaned, orig in cleaned_map.items():
        for canon in CANONICAL:
            if mapped[canon]:
                continue
            for var in VARIANTS.get(canon, []):
                if var and (var in cleaned or cleaned in var):
                    mapped[canon] = orig
                    break

    # ----------------------------------------------------
    # 3) token intersection (handles messy names)
    # ----------------------------------------------------
    cleaned_tokens_map = {c: set(c.split()) for c in cleaned_map.keys()}

    for canon in CANONICAL:
        if mapped[canon]:
            continue

        canon_tokens = set(" ".join(VARIANTS.get(canon, [])).split())
        best = None
        best_score = 0

        for cleaned, orig in cleaned_map.items():
            inter = len(cleaned_tokens_map[cleaned] & canon_tokens)
            score = inter / (1 + len(cleaned_tokens_map[cleaned]))

            if score > best_score and score > 0:
                best_score = score
                best = orig

        if best and best_score > 0.1:
            mapped[canon] = best

    # ----------------------------------------------------
    # 4) fuzzy matching (for typos)
    # ----------------------------------------------------
    if fuzzy:
        cleaned_keys = list(cleaned_map.keys())
        for canon in CANONICAL:
            if mapped[canon]:
                continue

            for var in VARIANTS.get(canon, []):
                matches = get_close_matches(var, cleaned_keys, n=1, cutoff=fuzzy_cutoff)
                if matches:
                    mapped[canon] = cleaned_map[matches[0]]
                    break

    # ----------------------------------------------------
    # 5) final fallback rules (very important)
    # ----------------------------------------------------
    for cleaned, orig in cleaned_map.items():

        # Prefer category/group
        if not mapped["item_category"] and any(t in cleaned for t in [
            "group", "material group", "item group", "merchandise category"
        ]):
            mapped["item_category"] = orig

        # Fix sales type names
        if not mapped["invoice_type"] and "sales" in cleaned and "type" in cleaned:
            mapped["invoice_type"] = orig

    return mapped
