import sys
import re
import requests
import pandas as pd
from PyQt6 import QtWidgets, QtCore
from datetime import datetime
from dateutil.parser import parse
import logging
import os
from requests.auth import HTTPDigestAuth

# --------------------------
# ScholarOne GUI App v2.2 (your provided file, unchanged)
# --------------------------

API_BASE_URL = "https://mc-api.manuscriptcentral.com"

# Endpoints config
ENDPOINTS = {
    "getSubmissionInfoFull": {"path": "/api/s1m/v9/submissions/full/metadata/submissionids", "requires_date": False, "id_kind": "submissionIds"},
    "getDocumentInfoFull": {"path": "/api/s1m/v9/submissions/full/metadata/documentids", "requires_date": False, "id_kind": "documentIds"},
    "getPersonInfoFullID": {"path": "/api/s1m/v7/person/full/personids/search", "requires_date": False, "id_kind": "personIds"},
    "getPersonInfoFullEmail": {"path": "/api/s1m/v7/person/full/email/search", "requires_date": False, "id_kind": "emails"},
    "getAuthorInfoFull": {"path": "/api/s1m/v3/submissions/full/contributors/authors/submissionids", "requires_date": False, "id_kind": "submissionIds"},
    "getEditorAssignmentsByDate": {"path": "/api/s1m/v1/submissions/full/editorAssignmentsByDate", "requires_date": True, "id_kind": None},
    "getIDsByDate": {"path": "/api/s1m/v4/submissions/full/idsByDate", "requires_date": True, "id_kind": None},
    "getSubmissionMetadataInfo": {"path": "/api/s1m/v3/submissions/full/metadatainfo/submissionids", "requires_date": False, "id_kind": "submissionIds"},
    "getDocumentMetadataInfo": {"path": "/api/s1m/v3/submissions/full/metadatainfo/documentids", "requires_date": False, "id_kind": "documentIds"},
    "getSubmissionReviewerInfoFull": {"path": "/api/s1m/v2/submissions/full/reviewer/submissionids", "requires_date": False, "id_kind": "submissionIds"},
    "getDocumentReviewerInfoFull": {"path": "/api/s1m/v2/submissions/full/reviewer/documentids", "requires_date": False, "id_kind": "documentIds"},
    "getSubmissionVersions": {"path": "/api/s1m/v2/submissions/full/revisions/submissionids", "requires_date": False, "id_kind": "submissionIds"},
    "getDocumentVersions": {"path": "/api/s1m/v2/submissions/full/revisions/documentids", "requires_date": False, "id_kind": "documentIds"},
}

SITE_LIST = [
    "deca", "isr", "inte", "ijoc", "ijds", "ijoo", "ite", "ms", "msom",
    "msomconference", "mksc", "mathor", "opre", "serv", "stratsci", "ssy",
    "orgsci", "transci"
]

DEFAULT_USERNAME = "INFORMS_Informs"
DEFAULT_API_KEY  = "ZUMQBXYNKLA8F25I"

def flatten_json(obj, prefix="site"):
    result = []
    def recurse(o, path=None, index=None):
        if path is None:
            path = []
        if isinstance(o, dict):
            for k, v in o.items():
                recurse(v, path + [k])
        elif isinstance(o, list):
            for i, item in enumerate(o):
                recurse(item, path, index=i)
        else:
            flat_key = ".".join(path)
            if index is not None:
                flat_key = f"{flat_key}_{index+1}"
            if flat_key in flat:
                suffix = 2
                while f"{flat_key}_{suffix}" in flat:
                    suffix += 1
                flat_key = f"{flat_key}_{suffix}"
            flat[flat_key] = o

    content = obj.get("Response", {}).get("result", {}).get("submission") or obj.get("Response", {}).get("result", {}) or obj.get("result", {})
    if isinstance(content, list):
        for item in content:
            flat = {"site_name": prefix}
            recurse(item, [])
            result.append(flat)
    else:
        flat = {"site_name": prefix}
        recurse(obj, [])
        result.append(flat)

    return result

class ScholarOneAPITool(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ScholarOne API Tool")
        self.resize(900, 700)
        self.layout = QtWidgets.QVBoxLayout(self)

        # Endpoint selector
        row1 = QtWidgets.QHBoxLayout()
        self.endpoint_label = QtWidgets.QLabel("Endpoint:")
        self.endpoint_selector = QtWidgets.QComboBox()
        self.endpoint_selector.addItems(ENDPOINTS.keys())
        self.endpoint_selector.currentIndexChanged.connect(self.toggle_date_fields)
        row1.addWidget(self.endpoint_label)
        row1.addWidget(self.endpoint_selector)

        # Sites (multi-select)
        self.site_label = QtWidgets.QLabel("Sites (CTRL/Shift to select multiple):")
        self.site_list = QtWidgets.QListWidget()
        self.site_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.site_list.addItems(SITE_LIST)
        self.site_list.setMaximumHeight(120)

        # Date filters
        row2 = QtWidgets.QHBoxLayout()
        self.start_date_label = QtWidgets.QLabel("From (local):")
        self.start_date_input = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.start_date_input.setCalendarPopup(True)
        self.end_date_label = QtWidgets.QLabel("To (local):")
        self.end_date_input = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.end_date_input.setCalendarPopup(True)
        row2.addWidget(self.start_date_label); row2.addWidget(self.start_date_input)
        row2.addWidget(self.end_date_label);   row2.addWidget(self.end_date_input)

        # IDs box
        self.id_entry_label = QtWidgets.QLabel("Submission/Document/Person IDs (any separators):")
        self.id_entry = QtWidgets.QPlainTextEdit()
        self.id_entry.setPlaceholderText("e.g. 12345 67890; 'A123' | B456 C789")
        self.id_entry.textChanged.connect(self.format_ids_vertically)
        self.id_entry.setMaximumHeight(120)

        # Buttons
        row3 = QtWidgets.QHBoxLayout()
        self.run_button = QtWidgets.QPushButton("Run")
        self.export_button = QtWidgets.QPushButton("Export to Excel")
        self.run_button.clicked.connect(self.run_query)
        self.export_button.clicked.connect(self.export_to_excel)
        row3.addWidget(self.run_button); row3.addWidget(self.export_button)

        # Log/output
        self.output = QtWidgets.QPlainTextEdit()
        self.output.setReadOnly(True)

        # Layout
        self.layout.addLayout(row1)
        self.layout.addWidget(self.site_label)
        self.layout.addWidget(self.site_list)
        self.layout.addLayout(row2)
        self.layout.addWidget(self.id_entry_label)
        self.layout.addWidget(self.id_entry)
        self.layout.addLayout(row3)
        self.layout.addWidget(self.output)

        self.toggle_date_fields()

        self._last_df = None

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.output.appendPlainText(f"[{ts}] {msg}")

    def toggle_date_fields(self):
        endpoint_key = self.endpoint_selector.currentText()
        needs = ENDPOINTS[endpoint_key]["requires_date"]
        self.start_date_label.setEnabled(needs); self.start_date_input.setEnabled(needs)
        self.end_date_label.setEnabled(needs);   self.end_date_input.setEnabled(needs)

    def format_ids_vertically(self):
        cursor = self.id_entry.textCursor()
        pos = cursor.position()
        raw = self.id_entry.toPlainText()
        ids = self.normalize_ids(raw)
        self.id_entry.blockSignals(True)
        self.id_entry.setPlainText("\n".join(ids))
        cursor.setPosition(min(pos, len(self.id_entry.toPlainText())))
        self.id_entry.setTextCursor(cursor)
        self.id_entry.blockSignals(False)

    def normalize_ids(self, id_text):
        return [s.strip() for s in re.split(r"[\s,;|]+", id_text.strip()) if s.strip()]

    def convert_to_utc(self, date_str: str) -> str:
        # Accepts from QDateTimeEdit -> str; allows many formats
        try:
            dt = parse(date_str)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            # fallback if user only changes date, not time
            try:
                dt = datetime.strptime(date_str, "%m/%d/%Y %I:%M %p")
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                try:
                    dt = datetime.strptime(date_str, "%m/%d/%Y")
                    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    raise ValueError(f"Unrecognized date format: {date_str}")

    def run_query(self):
        self.submit_request()

    def submit_request(self):
        username = DEFAULT_USERNAME; api_key = DEFAULT_API_KEY
        sites = [item.text() for item in self.site_list.selectedItems()]
        if not sites:
            self.log("⚠️ No sites selected.")
            return

        endpoint_key = self.endpoint_selector.currentText(); endpoint_conf = ENDPOINTS[endpoint_key]
        endpoint_path = endpoint_conf["path"]

        session = requests.Session(); session.auth = HTTPDigestAuth(username, api_key)
        full_entries = []

        if endpoint_conf["requires_date"]:
            try:
                start_date = self.convert_to_utc(self.start_date_input.text())
                end_date   = self.convert_to_utc(self.end_date_input.text())
            except Exception as e:
                self.log(f"❌ Date error: {e}")
                return

        ids = self.normalize_ids(self.id_entry.toPlainText())
        id_kind = endpoint_conf.get("id_kind")

        for site in sites:
            params = {"_type": "json", "site_name": site}
            if endpoint_conf["requires_date"]:
                params.update({"from_time": start_date, "to_time": end_date})

            # Build URL
            url = f"{API_BASE_URL}{endpoint_path}"

            # GET with ids batched in query (when applicable)
            if id_kind and ids:
                # 25-per batch (typical S1M behavior)
                batches = [ids[i:i+25] for i in range(0, len(ids), 25)]
            else:
                batches = [[None]]

            for batch in batches:
                q = params.copy()
                if id_kind and batch != [None]:
                    # join with comma; S1M expects ids=1,2,3 (no quotes)
                    q["ids"] = ",".join(batch)

                try:
                    self.log(f"🔎 GET {url} {q}")
                    r = session.get(url, params=q, timeout=60)
                    self.log(f"HTTP {r.status_code}")
                    if r.status_code != 200:
                        txt = r.text[:500] if r.text else "<no body>"
                        self.log(f"Headers: {dict(r.headers)}")
                        self.log(f"Body: {txt}")
                        continue
                    if not r.text or not r.text.strip():
                        self.log("⚠️ Empty body.")
                        continue
                    j = r.json()
                    rows = flatten_json(j, prefix=site)
                    full_entries.extend(rows)
                    self.log(f"✅ {site}: +{len(rows)} rows")
                except Exception as e:
                    self.log(f"❌ {site} error: {type(e).__name__}: {e}")

        if full_entries:
            df = pd.DataFrame(full_entries)
            self._last_df = df
            self.log(f"📊 Total rows: {len(df)}")
        else:
            self._last_df = None
            self.log("No data to display/export.")

    def export_to_excel(self):
        if self._last_df is None or self._last_df.empty:
            self.log("Nothing to export.")
            return
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        outname = f"ScholarOne_API_Export_{now}.xlsx"
        try:
            self._last_df.to_excel(outname, index=False)
            self.log(f"💾 Exported to {outname}")
        except Exception as e:
            self.log(f"Export error: {e}")

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = ScholarOneAPITool()
    window.show()
    sys.exit(app.exec())
