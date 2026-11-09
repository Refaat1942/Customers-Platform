from PyQt6 import QtWidgets
from ui_helpers import PandasModel
import business_analysis as ba
import pandas as pd


def setup_business_tab(self):
    layout = QtWidgets.QVBoxLayout(self.tab_business)

    filter_row = QtWidgets.QHBoxLayout()

    filter_row.addWidget(QtWidgets.QLabel("Branch:"))
    self.biz_filter_branch = QtWidgets.QComboBox()
    self.biz_filter_branch.setFixedWidth(200)
    filter_row.addWidget(self.biz_filter_branch)

    filter_row.addWidget(QtWidgets.QLabel("Sales Type:"))
    self.biz_filter_type = QtWidgets.QComboBox()
    self.biz_filter_type.setFixedWidth(200)
    filter_row.addWidget(self.biz_filter_type)

    filter_row.addWidget(QtWidgets.QLabel("Season:"))
    self.biz_filter_season = QtWidgets.QComboBox()
    self.biz_filter_season.setFixedWidth(140)
    self.biz_filter_season.addItems(["All", "Winter", "Spring", "Summer", "Autumn"])
    filter_row.addWidget(self.biz_filter_season)

    btn_run = QtWidgets.QPushButton("Run Business Analysis")
    btn_run.clicked.connect(lambda: run_business_analysis(self))
    filter_row.addWidget(btn_run)

    filter_row.addStretch()
    layout.addLayout(filter_row)

    self.biz_table = QtWidgets.QTableView()
    layout.addWidget(self.biz_table)

    btn_export = QtWidgets.QPushButton("Export Business Report")
    btn_export.clicked.connect(lambda: export_business(self))
    layout.addWidget(btn_export)

    populate_biz_filters(self)


def populate_biz_filters(self):
    if self.df is None or self.df.empty:
        return

    df = self.df
    branch_col = self.colmap.get("branch")
    type_col = self.colmap.get("invoice_type")

    self.biz_filter_branch.clear()
    self.biz_filter_branch.addItem("All")
    if branch_col and branch_col in df.columns:
        self.biz_filter_branch.addItems(
            sorted(df[branch_col].dropna().astype(str).unique())
        )

    self.biz_filter_type.clear()
    self.biz_filter_type.addItem("All")
    if type_col and type_col in df.columns:
        self.biz_filter_type.addItems(
            sorted(df[type_col].dropna().astype(str).unique())
        )


# ----------------------------------------------------------
# HELPER
# ----------------------------------------------------------
def normalize(v):
    return v.strip() if v and v.strip() else "All"


def run_business_analysis(self):
    print("RUN BUSINESS ANALYSIS CLICKED")

    if self.df is None or self.df.empty:
        QtWidgets.QMessageBox.information(
            self, "No Data", "Please load data first"
        )
        return

    df = self.df.copy()

    branch_col = self.colmap.get("branch")
    type_col = self.colmap.get("invoice_type")
    date_col = self.colmap.get("invoice_date")

    # ✅ Normalize values
    b = normalize(self.biz_filter_branch.currentText())
    t = normalize(self.biz_filter_type.currentText())
    s = normalize(self.biz_filter_season.currentText())

    # ---------- Branch ----------
    if b != "All" and branch_col and branch_col in df.columns:
        df = df[df[branch_col].astype(str) == b]

    # ---------- Sales Type ----------
    if t != "All" and type_col and type_col in df.columns:
        df = df[df[type_col].astype(str) == t]

    # ---------- Season ----------
    if s != "All" and date_col and date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df["season"] = df[date_col].dt.month.map(ba.month_to_season)
        df = df[df["season"] == s]

    if df.empty:
        QtWidgets.QMessageBox.information(
            self, "No Results", "No data after applying Business filters"
        )
        self.biz_table.setModel(PandasModel(pd.DataFrame()))
        return

    result = ba.full_customer_business(df, self.colmap)

    if result.empty:
        QtWidgets.QMessageBox.information(
            self, "No Results", "Business analysis returned no data"
        )
        self.biz_table.setModel(PandasModel(pd.DataFrame()))
        return

    display = result[
        [
            "phone",
            "name",
            "branch",
            "total_spent_display",
            "visits",
            "top_material",
            "top_category",
            "top_sales_type",
            "top_season",
            "loyalty_flag",
        ]
    ].rename(columns={
        "phone": "Customer Phone",
        "name": "Customer Name",
        "branch": "Branch",
        "total_spent_display": "Total Spend",
        "visits": "Visits",
        "top_material": "Top Material",
        "top_category": "Top Category",
        "top_sales_type": "Sales Type",
        "top_season": "Top Season",
        "loyalty_flag": "Loyal Customer",
    })

    self.biz_table.setModel(PandasModel(display))
    self.biz_table.resizeColumnsToContents()
    self.biz_table.horizontalHeader().setStretchLastSection(True)

    QtWidgets.QMessageBox.information(
        self, "Done", "Business analysis completed successfully"
    )


def export_business(self):
    model = self.biz_table.model()
    if model is None or model._df.empty:
        return

    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        self, "Save Business Report", "business_report.xlsx", "Excel Files (*.xlsx)"
    )
    if path:
        model._df.to_excel(path, index=False)
