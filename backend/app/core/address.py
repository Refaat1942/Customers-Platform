"""District extraction from free-text addresses (ported from legacy/area_tab.py)."""

import re

FILLER_WORDS = {
    "city", "street", "st", "road", "rd", "avenue", "ave", "district", "building",
    "bldg", "villa", "apt", "apartment", "floor", "block", "no", "flat",
    "شارع", "ش", "عمارة", "شقة", "الدور", "دور", "مدينة", "برج", "رقم",
}

_WORD = re.compile(r"[^A-Za-z؀-ۿ]+")


def extract_district(address) -> str:
    if not isinstance(address, str) or not address.strip():
        return "Unknown"

    text = re.sub(r"[,/\\\-]+", " ", address)
    parts = re.sub(r"\s+", " ", text).strip().split()

    for i, p in enumerate(parts):
        if p.lower() == "district":
            # "Maadi district" or "district Maadi"
            for j in (i - 1, i + 1):
                if 0 <= j < len(parts):
                    w = _WORD.sub("", parts[j])
                    if len(w) > 1 and w.lower() not in FILLER_WORDS:
                        return w.capitalize()

    for p in parts:
        w = _WORD.sub("", p)
        if len(w) > 1 and w.lower() not in FILLER_WORDS:
            return w.capitalize()

    return "Unknown"
