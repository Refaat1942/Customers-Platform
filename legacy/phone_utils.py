import re


def digits_only(x):
    """
    Extract only digits from any input and remove .0 and spaces.
    """
    if x is None:
        return ""
    s = str(x).strip()

    # Remove .0 from Excel numbers
    if s.endswith(".0"):
        s = s[:-2]

    # Extract digits only
    return "".join(ch for ch in s if ch.isdigit())


def normalize_egy_phone(x):
    """
    Normalize Egyptian mobile numbers.
    Ensures returned value is ALWAYS a correct 11-digit number when possible.
    Fix Excel issues where leading zero is dropped.
    """

    s = digits_only(x)

    # Nothing to do
    if not s:
        return ""

    # Valid prefixes
    VALID_PREFIXES = ["010", "011", "012", "015"]

    # -----------------------------------------
    # CASE 1 — already correct (01xxxxxxxxx)
    # -----------------------------------------
    if len(s) == 11 and s.startswith("01"):
        return s

    # -----------------------------------------
    # CASE 2 — Excel removed leading zero
    # Example: 1033316088 → 01033316088
    # -----------------------------------------
    if len(s) == 10 and s.startswith(("10", "11", "12", "15")):
        return "0" + s

    # -----------------------------------------
    # CASE 3 — 11 digits but wrong prefix (fix by adding leading zero)
    # -----------------------------------------
    if len(s) == 11 and not s.startswith("01"):
        fixed = "0" + s[-10:]
        if fixed[:3] in VALID_PREFIXES:
            return fixed

    # -----------------------------------------
    # CASE 4 — starts with 20 (country code)
    # Example: 201033316088 → 01033316088
    # -----------------------------------------
    if s.startswith("20"):
        rest = s[2:]
        if len(rest) == 11 and rest.startswith("01"):
            return rest
        if len(rest) == 10:
            return "0" + rest

    # -----------------------------------------
    # CASE 5 — long number (search for valid pattern inside)
    # -----------------------------------------
    if len(s) > 11:
        for i in range(len(s) - 10):
            part = s[i:i+11]
            if part.startswith("01"):
                return part

    # -----------------------------------------
    # CASE 6 — short but has valid middle digits
    # -----------------------------------------
    if len(s) < 11:
        # Try to pad/match possible valid number
        if len(s) >= 9 and s[-10:].startswith(("10", "11", "12", "15")):
            return "0" + s[-10:]

    # -----------------------------------------
    # FINAL — return digits only but avoid empty
    # -----------------------------------------
    return s
