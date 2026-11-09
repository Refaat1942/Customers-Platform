from PyQt6 import QtWidgets, QtGui
import pandas as pd
import re
from ui_helpers import PandasModel
import business_analysis as ba


# ==========================================================
# SMART DISTRICT EXTRACTION (ONCE)
# ==========================================================
def extract_district(address):
    if not isinstance(address, str):
        return "Unknown"

    text = re.sub(r"[,/\\\-]+", " ", address)
    text = re.sub(r"\s+", " ", text).strip()

    filler_words = {
        "city","street","st","road","rd","avenue","ave",
        "district","building","villa","apt","apartment","floor","block"
    }

    parts = text.split()

    for i, p in enumerate(parts):
        if p.lower() == "district" and i + 1 < len(parts):
            return re.sub(r"[^A-Za-zأ-ي]+", "", parts[i + 1]).capitalize()

    for p in parts:
        w = re.sub(r"[^A-Za-zأ-ي]+", "", p)
        if w and w.lower() not in filler_words:
            return w.capitalize()

    return "Unknown"


# ==========================================================
# SETUP AREA TAB UI (UNCHANGED)
# ==========================================================
def setup_area_tab(self):
    layout = QtWidgets.QVBoxLayout(self.tab_area)
    title_font = QtGui.QFont()
    title_font.setPointSize(13)
    title_font.setBold(True)

    filter_row = QtWidgets.QHBoxLayout()
    self.area_branch_filter = QtWidgets.QComboBox()
    self.area_branch_filter.setFixedWidth(180)
    self.area_branch_filter.currentIndexChanged.connect(
        lambda: run_area_analytics(self)
    )
    filter_row.addWidget(QtWidgets.QLabel("Branch:"))
    filter_row.addWidget(self.area_branch_filter)

    self.area_district_filter = QtWidgets.QComboBox()
    self.area_district_filter.setFixedWidth(200)
    self.area_district_filter.currentIndexChanged.connect(
        lambda: run_area_analytics(self)
    )
    filter_row.addWidget(QtWidgets.QLabel("District:"))
    filter_row.addWidget(self.area_district_filter)

    filter_row.addStretch()
    layout.addLayout(filter_row)

    btn = QtWidgets.QPushButton("Run Area Analytics")
    btn.clicked.connect(lambda: run_area_analytics(self))
    layout.addWidget(btn)

    for lbl, attr in [
        ("Area Performance", "tbl_area_main"),
        ("Top Districts per Branch", "tbl_area_top"),
        ("Weak / Underperforming Districts", "tbl_area_weak"),
    ]:
        lab = QtWidgets.QLabel(lbl)
        lab.setFont(title_font)
        layout.addWidget(lab)
        table = QtWidgets.QTableView()
        setattr(self, attr, table)
        layout.addWidget(table)

    exp = QtWidgets.QPushButton("Export Area Report")
    exp.clicked.connect(lambda: export_area_report(self))
    layout.addWidget(exp)


# ==========================================================
# MAIN LOGIC (CACHED & OPTIMIZED)
# ==========================================================
def run_area_analytics(self):
    if not hasattr(self, "df") or self.df.empty:
        return

    if not hasattr(self, "_area_cache"):
        self._area_cache = {}

    df_base = self.df
    branch_col = self.colmap.get("branch")
    phone_col = self.colmap.get("phone")
    price_col = self.colmap.get("item_price")
    addr_col = self.colmap.get("address")

    # ---------- Prepare district ONCE ----------
    if "district" not in df_base.columns:
        df_base = df_base.copy()
        if addr_col in df_base.columns:
            df_base["district"] = df_base[addr_col].apply(extract_district)
        else:
            df_base["district"] = "Unknown"
        self.df = df_base

    # ---------- Populate filters ONCE ----------
    if not hasattr(self, "_area_filters_loaded"):
        self.area_branch_filter.blockSignals(True)
        self.area_branch_filter.clear()
        self.area_branch_filter.addItem("All")
        self.area_branch_filter.addItems(
            sorted(df_base[branch_col].dropna().astype(str).unique())
        )
        self.area_branch_filter.blockSignals(False)

        self.area_district_filter.blockSignals(True)
        self.area_district_filter.clear()
        self.area_district_filter.addItem("All")
        self.area_district_filter.addItems(
            sorted(df_base["district"].dropna().unique())
        )
        self.area_district_filter.blockSignals(False)

        self._area_filters_loaded = True

    sel_branch = self.area_branch_filter.currentText()
    sel_dist = self.area_district_filter.currentText()
    cache_key = (sel_branch, sel_dist)

    if cache_key in self._area_cache:
        _apply_area(self, self._area_cache[cache_key])
        return

    # ---------- Filter ----------
    df = df_base
    if sel_branch != "All":
        df = df[df[branch_col].astype(str) == sel_branch]
    if sel_dist != "All":
        df = df[df["district"] == sel_dist]

    # ---------- Aggregations ----------
    grp = df.groupby("district").agg(
        Total_Sales=(price_col, "sum"),
        Unique_Customers=(phone_col, "nunique"),
    ).reset_index()

    grp["Spending_per_customer"] = (
        grp["Total_Sales"] / grp["Unique_Customers"].replace(0, 1)
    )

    grp = grp.sort_values("Total_Sales", ascending=False)

    # ---------- Branch + District ----------
    bd = df.groupby([branch_col, "district"]).agg(
        total_sales=(price_col, "sum"),
        unique_customers=(phone_col, "nunique"),
    ).reset_index()
    bd["spending_per_customer"] = (
        bd["total_sales"] / bd["unique_customers"].replace(0, 1)
    )

    # ---------- Weak districts ----------
    weak = grp[grp["Unique_Customers"] > 0].sort_values(
        "Spending_per_customer"
    ).head(10)

    result = {
        "main": grp,
        "branch": bd,
        "weak": weak,
    }

    self._area_cache[cache_key] = result
    _apply_area(self, result)


def _apply_area(self, res):
    self.tbl_area_main.setModel(PandasModel(res["main"]))
    self.tbl_area_top.setModel(PandasModel(res["branch"]))
    self.tbl_area_weak.setModel(PandasModel(res["weak"]))

    self._area_report = res


# ==========================================================
# EXPORT (UNCHANGED)
# ==========================================================
def export_area_report(self):
    if not hasattr(self, "_area_report"):
        return

    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        self, "Save Area Report", "area_report.xlsx", "Excel Files (*.xlsx)"
    )
    if not path:
        return

    writer = pd.ExcelWriter(path, engine="xlsxwriter")
    self._area_report["main"].to_excel(writer, "District_Overall", index=False)
    self._area_report["branch"].to_excel(writer, "Branch_District", index=False)
    self._area_report["weak"].to_excel(writer, "Weak_Districts", index=False)
    writer.close()
