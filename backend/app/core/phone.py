"""Egyptian mobile number normalisation (ported from legacy/phone_utils.py)."""

VALID_PREFIXES = ("010", "011", "012", "015")


def digits_only(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if s.lower() in ("nan", "none", "nat"):
        return ""
    if s.endswith(".0"):  # Excel numbers
        s = s[:-2]
    return "".join(ch for ch in s if ch.isdigit())


def normalize_egy_phone(x) -> str:
    """Return an 11-digit 01xxxxxxxxx number when possible, else the raw digits."""
    s = digits_only(x)
    if not s:
        return ""

    if len(s) == 11 and s.startswith("01"):
        return s

    # Excel dropped the leading zero: 1033316088 -> 01033316088
    if len(s) == 10 and s.startswith(("10", "11", "12", "15")):
        return "0" + s

    if len(s) == 11 and not s.startswith("01"):
        fixed = "0" + s[-10:]
        if fixed[:3] in VALID_PREFIXES:
            return fixed

    # Country code: 201033316088 / 2001033316088
    if s.startswith("20"):
        rest = s[2:]
        if len(rest) == 11 and rest.startswith("01"):
            return rest
        if len(rest) == 10 and rest.startswith(("10", "11", "12", "15")):
            return "0" + rest

    if len(s) > 11:
        for i in range(len(s) - 10):
            part = s[i:i + 11]
            if part[:3] in VALID_PREFIXES:
                return part

    return s


def is_valid_egy_mobile(s) -> bool:
    return isinstance(s, str) and len(s) == 11 and s[:3] in VALID_PREFIXES
