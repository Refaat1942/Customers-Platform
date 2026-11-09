import sys
import pandas as pd
from PyQt6 import QtWidgets
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QPushButton
)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt, QTimer

from data_store import DataStore

# Helpers
from phone_utils import normalize_egy_phone
from column_mapper import find_columns
from address_utils import parse_address

# Tabs
from filters_tab import (
    setup_filters_tab,
    populate_filter_widgets,
    update_table_view,
)
from customer_tab import setup_customer_tab
from business_tab import setup_business_tab
from ai_tab import setup_ai_tab
from overall_tab import setup_overall_tab, update_overall_metrics
from area_tab import setup_area_tab


# ============================================================
#                    SPLASH SCREEN
# ============================================================

class SplashScreen(QDialog):
    def __init__(self):
        super().__init__()

        # ❌ شيل شريط الويندوز
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self.setFixedSize(600, 420)
        self.setStyleSheet("""
            background-color: #ffffff;
            border-radius: 12px;
        """)

        main = QVBoxLayout(self)
        main.setContentsMargins(20, 20, 20, 20)

        # ---------------- TOP BAR ----------------
        top = QHBoxLayout()
        top.addStretch()

        btn_min = QPushButton("—")
        btn_min.setFixedSize(28, 28)
        btn_min.setStyleSheet("""
            QPushButton {
                border: none;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #eeeeee;
            }
        """)
        btn_min.clicked.connect(self.showMinimized)
        top.addWidget(btn_min)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 28)
        btn_close.setStyleSheet("""
            QPushButton {
                border: none;
                font-size: 16px;
                color: #b00020;
            }
            QPushButton:hover {
                background: #ffecec;
            }
        """)
        btn_close.clicked.connect(self.close)
        top.addWidget(btn_close)

        main.addLayout(top)

        # ---------------- CENTER ----------------
        center = QVBoxLayout()
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo = QLabel()
        pix = QPixmap("Lotus.png").scaled(
            160, 160,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        logo.setPixmap(pix)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(logo)

        title = QLabel("Customers Platform")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setStyleSheet("color: #1b5e20;")  # أخضر شيك
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(title)

        subtitle = QLabel("Business Intelligence Dashboard")
        subtitle.setFont(QFont("Segoe UI", 11))
        subtitle.setStyleSheet("color: #555555;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(subtitle)

        self.progress = QProgressBar()
        self.progress.setFixedWidth(320)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                height: 10px;
                border-radius: 5px;
                background: #eeeeee;
            }
            QProgressBar::chunk {
                border-radius: 5px;
                background-color: #2e7d32;
            }
        """)
        center.addWidget(self.progress)

        main.addLayout(center)

    def set_progress(self, v):
        self.progress.setValue(v)
        QtWidgets.QApplication.processEvents()



# ============================================================
#                      MAIN WINDOW
# ============================================================

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, splash=None):
        super().__init__()

        self.setWindowTitle("Customers Platform")
        self.resize(1500, 900)

        self.df = pd.DataFrame()
        self.filtered = pd.DataFrame()
        self.colmap = {}

        if splash:
            splash.set_progress(10)

        self.store = DataStore()
        self.store.init_db()

        if splash:
            splash.set_progress(30)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ================= TOP BUTTONS =================
        top = QHBoxLayout()

        self.btn_load = QPushButton("Load / Update Excel")
        self.btn_load.clicked.connect(self.load_excel)
        top.addWidget(self.btn_load)

        self.btn_reload = QPushButton("Reload From DB")
        self.btn_reload.clicked.connect(self.reload_from_db)
        top.addWidget(self.btn_reload)

        self.lbl_status = QLabel("No data loaded")
        top.addWidget(self.lbl_status)

        top.addStretch()

        self.btn_export = QPushButton("Export Filtered")
        self.btn_export.clicked.connect(self.export_filtered)
        top.addWidget(self.btn_export)

        layout.addLayout(top)

        # ================= SEARCH BAR =================
        search = QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search by phone or name...")
        self.search_input.returnPressed.connect(self.on_search)
        search.addWidget(self.search_input)

        btn_search = QPushButton("Search")
        btn_search.clicked.connect(self.on_search)
        search.addWidget(btn_search)

        layout.addLayout(search)

        # ================= TABS =================
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)

        self.tab_filters = QtWidgets.QWidget()
        self.tabs.addTab(self.tab_filters, "Filters")
        setup_filters_tab(self)

        self.tab_customer = QtWidgets.QWidget()
        self.tabs.addTab(self.tab_customer, "Customer Analysis")
        setup_customer_tab(self)

        self.tab_business = QtWidgets.QWidget()
        self.tabs.addTab(self.tab_business, "Business Analysis")
        setup_business_tab(self)

        self.tab_ai = QtWidgets.QWidget()
        self.tabs.addTab(self.tab_ai, "AI Recommendations")
        setup_ai_tab(self)

        self.tab_overall = QtWidgets.QWidget()
        self.tabs.addTab(self.tab_overall, "Overall Summary")
        setup_overall_tab(self)

        self.tab_area = QtWidgets.QWidget()
        self.tabs.addTab(self.tab_area, "Area Analytics")
        setup_area_tab(self)

        self.status = self.statusBar()

        # ===== AUTO LOAD FROM DB =====
        if self.store.has_data():
            if splash:
                splash.set_progress(60)
            self._post_load(self.store.load_all())
            self.lbl_status.setText("Loaded from DB")

        if splash:
            splash.set_progress(100)

    # ================= DATA =================

    def load_excel(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose Excel", "", "Excel Files (*.xlsx *.xls)"
        )
        if not path:
            return

        if not self.store.has_data():
            df = self.store.load_excel_full(path)
        else:
            df = self.store.update_from_excel(path, self.colmap.get("invoice_date"))

        self._post_load(df)
        self.lbl_status.setText("Loaded from Excel")

    def reload_from_db(self):
        self._post_load(self.store.load_all())
        self.lbl_status.setText("Reloaded from DB")

    def _post_load(self, df):
        if df is None or df.empty:
            return

        self.colmap = find_columns(df.columns)

        if self.colmap.get("phone"):
            df[self.colmap["phone"]] = df[self.colmap["phone"]].apply(normalize_egy_phone)

        if self.colmap.get("address") and "district" not in df.columns:
            extracted = df[self.colmap["address"]].apply(parse_address)
            df["district"] = extracted.apply(lambda x: x.get("district"))

        self.df = df.copy()
        self.filtered = df.copy()

        populate_filter_widgets(self)
        update_table_view(self, self.filtered)
        update_overall_metrics(self)

    # ================= SEARCH =================

    def on_search(self):
        if self.df.empty:
            return

        text = self.search_input.text().strip()
        if not text:
            return

        res = pd.DataFrame()

        if self.colmap.get("name"):
            res = self.df[
                self.df[self.colmap["name"]]
                .astype(str)
                .str.contains(text, case=False, na=False)
            ]

        if self.colmap.get("phone"):
            n = normalize_egy_phone(text)
            r2 = self.df[
                self.df[self.colmap["phone"]]
                .astype(str)
                .str.contains(n, na=False)
            ]
            res = pd.concat([res, r2]).drop_duplicates()

        self.filtered = res
        update_table_view(self, self.filtered)

    # ================= EXPORT =================

    def export_filtered(self):
        if self.filtered.empty:
            return

        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save CSV", "filtered.csv", "CSV Files (*.csv)"
        )
        if path:
            self.filtered.to_csv(path, index=False, encoding="utf-8-sig")


# ============================================================
#                            MAIN
# ============================================================

def main():
    app = QtWidgets.QApplication(sys.argv)

    splash = SplashScreen()
    splash.show()

    def start():
        try:
            win = MainWindow(splash)
            splash.close()
            win.show()
        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(
                None,
                "Startup Error",
                str(e)
            )
            sys.exit(1)

    QTimer.singleShot(300, start)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
