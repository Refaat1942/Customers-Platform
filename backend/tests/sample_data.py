"""Generates a fake sales Excel file shaped like the pharmacy exports."""

import random
from datetime import datetime, timedelta

import pandas as pd

BRANCHES = ["Maadi", "Zamalek", "Nasr City", "Heliopolis"]
DISTRICTS = ["Maadi", "Degla", "Zamalek", "Abbas", "Korba", "Sheraton"]
TYPES = ["Cash", "Delivery", "Insurance"]
GROUPS = ["Medicine", "Cosmetics", "Baby Care", "Supplements"]
ITEMS = ["Panadol", "Vitamin C", "Baby Milk", "Sunscreen", "Antinal", "Omega 3"]


def make_rows(n_customers=60, seed=1, end=datetime(2026, 10, 31)):
    rnd = random.Random(seed)
    rows = []
    for c in range(n_customers):
        phone = f"10{rnd.randint(10000000, 99999999)}"  # leading zero lost, like Excel
        name = f"Customer {c}"
        branch = rnd.choice(BRANCHES)
        address = f"{rnd.randint(1, 90)} Street, {rnd.choice(DISTRICTS)} district, Cairo"
        last = end - timedelta(days=rnd.choice([3, 20, 45, 100, 200]))
        for v in range(rnd.randint(1, 8)):
            d = last - timedelta(days=v * rnd.randint(5, 40), hours=rnd.randint(0, 10))
            inv = f"INV{c:03d}{v:02d}"
            for _ in range(rnd.randint(1, 3)):
                rows.append({
                    "Mobile No": phone, "Customer Name": name, "Branch Name": branch,
                    "Customer Address": address, "Invoice Number": inv, "Posting Date": d,
                    "Sales Type_name": rnd.choice(TYPES), "Material": rnd.randint(1000, 9999),
                    "Material Description": rnd.choice(ITEMS),
                    "Material Group": rnd.choice(GROUPS), "Qty": rnd.randint(1, 3),
                    "Net Amount": round(rnd.uniform(50, 3000), 2),
                })
    return pd.DataFrame(rows)


def write_sample(path, **kw):
    make_rows(**kw).to_excel(path, index=False)
    return path


if __name__ == "__main__":
    import sys
    write_sample(sys.argv[1] if len(sys.argv) > 1 else "sample_sales.xlsx", n_customers=400)
