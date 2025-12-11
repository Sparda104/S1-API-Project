# scholarone_gui_app.py
# ScholarOne API GUI Tool (GET-based) with Digest Auth and JSON->Excel export.
# Updated to support email-based queries for getPersonInfoFullEmail by sending
# ?primary_email=<value> and batching at 1 per request.

import sys
import os
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

import requests
from requests.auth import HTTPDigestAuth

import pandas as pd
from PyQt6 import QtWidgets, QtCore

# -----------------------------
# Basic logging to console + file
# -----------------------------
LOG_NAME = f"scholarone_gui_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_NAME, encoding="utf-8")
    ],
)

# -----------------------------
# Config
# -----------------------------
API_BASE_URL = "https://mc-api.manuscriptcentral.com"

# Credentials can be pulled from env vars for safety; hardcode if you must.
API_USERNAME = os.environ.get("S1M_USER", "INFORMS_Informs")
API_PASSWORD = os.environ.get("S1M_PASS", "ZUMQBXYNKLA8F25I")

# Endpoints catalog. Only getPersonInfoFullEmail was changed to include id_kind/emails behavior.
ENDPOINTS: Dict[str, Dict[str, Any]] = {
    # Submission / Document metadata (IDs required)
    "getSubmissionInfoFull": {
        "path": "/api/s1m/v9/submissions/full/metadata/submissionids",
        "requires_date": False,
        # leave ids behavior as-is (default 'ids' will be used below)
    },
    "getDocumentInfoFull": {
        "path": "/api/s1m/v9/submissions/full/metadata/documentids",
        "requires_date": False,
    },

    # Person endpoints
    "getPersonInfoFullID": {
        "path": "/api/s1m/v7/person/full/personids/search",
        "requires_date": False,
        # this uses numeric IDs; no special id_kind needed
    },
    "getPersonInfoFullEmail": {
        "path": "/api/s1m/v7/person/full/email/search",
        "requires_date": False,
        # >>> UPDATED <<<
        # Tell the app this endpoint uses emails, the API expects `primary_email`,
        # and we should send one email per request.
        "id_kind": "emails",
        "id_param": "primary_email",
        "batch_size": 1,
    },

    # Contributors
    "getAuthorInfoFull": {
        "path": "/api/s1m/v3/submissions/full/contributors/authors/submissionids",
        "requires_date": False,
    },

    # Date-based endpoints
    "getEditorAssignmentsByDate": {
        "path": "/api/s1m/v1/submissions/full/editorAssignmentsByDate",
        "requires_date": True,
    },
    "getIDsByDate": {
        "path": "/api/s1m/v4/submissions/full/idsByDate",
        "requires_date": True,
    },

    # Metadata info (IDs required)
    "getSubmissionMetadataInfo": {
        "path": "/api/s1m/v3/submissions/full/metadatainfo/submissionids",
        "requires_date": False,
    },
    "getDocumentMetadataInfo": {
        "path": "/api/s1m/v3/submissions/full/metadatainfo/documentids",
        "requires_date": False,
    },

    # Reviewer info (IDs required)
    "getSubmissionReviewerInfoFull": {
        "path": "/api/s1m/v2/submissions/full/reviewer/submissionids",
        "requires_date": False,
    },
    "getDocumentReviewerInfoFull": {
        "path": "/api/s1m/v2/submissions/full/reviewer/documentids",
        "requires_date": False,
    },

    # Versions (IDs required)
    "getSubmissionVersions": {
        "path": "/api/s1m/v2/submissions/full/revisions/submissionids",
        "requires_date": False,
    },
    "getDocumentVersions": {
        "path": "/api/s1m/v2/submissions/full/revisions/documentids",
        "requires_date": False,
    },
}

SITE_LIST = [
    "deca", "isr", "inte", "ijoc", "ijds", "ijoo", "ite", "ms", "msom",
    "msomconference", "mksc", "mathor", "opre", "serv", "stratsci", "ssy",
    "orgsci", "transci"
]


# -----------------------------
# Helpers
# -----------------------------
def to_utc_date_str(qdate: QtCore.QDate, end_of_day: bool = False) -> str:
    # ScholarOne expects UTC Z times. We'll force 00:00:00 or 23:59:59.
    if end_of_day:
        return qdate.toString("yyyy-MM-dd") + "T23:59:59Z"
    return qdate.toString("yyyy-MM-dd") + "T00:00:00Z"


def flatten_json(obj: Any, prefix: str = "site") -> List[Dict[str, Any]]:
    """
    Flattens the JSON Response into row-like dicts. Attempts to find
    Response.result.submission list; if not found, flattens top-level.
    """
    rows: List[Dict[str, Any]] = []

    def _recurse(o, parent_key=""):
        items = {}
        if isinstance(o, dict):
            for k, v in o.items():
                new_key = f"{parent_key}.{k}" if parent_key else k
                items.update(_recurse(v, new_key))
        elif isinstance(o, list):
            # produce separate keys per index
            for i, v in enumerate(o, start=1):
                new_key = f"{parent_key}_{i}" if parent_key else str(i)
                items.update(_recurse(v, new_key))
        else:
            items[parent_key] = o
        return items

    # Heuristic: the typical payload is {"Response":{"result":{"submission":[...]}}}
    try:
        submissions = obj.get("Response", {}).get("result", {}).get("submission")
        if isinstance(submissions, list):
            for item in submissions:
                flat = {"site_name": prefix}
                flat.update(_recurse(item))
                rows.append(flat)
            return rows
    except Exception:
        pass

    # Fallback: flatten entire payload as one row
    flat = {"site_name": prefix}
    flat.update(_recurse(obj))
    rows.append(flat)
    return rows


def as_csv(items: List[str]) -> str:
    return ",".join(items)


# -----------------------------
# Main GUI
# -----------------------------
class ScholarOneAPITool(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ScholarOne API Tool")
        self.resize(920, 720)

        self.layout = QtWidgets.QVBoxLayout(self)

        # Controls
        row1 = QtWidgets.QHBoxLayout()
        self.endpoint_label = QtWidgets.QLabel("Endpoint:")
        self.endpoint_combo = QtWidgets.QComboBox()
        self.endpoint_combo.addItems(ENDPOINTS.keys())
        self.endpoint_combo.currentIndexChanged.connect(self.toggle_date_fields)
        row1.addWidget(self.endpoint_label)
        row1.addWidget(self.endpoint_combo)

        row2 = QtWidgets.QHBoxLayout()
        self.site_label = QtWidgets.QLabel("Sites (multi-select):")
        self.site_list = QtWidgets.QListWidget()
        self.site_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.site_list.addItems(SITE_LIST)
        row2.addWidget(self.site_label)
        row2.addWidget(self.site_list)

        row3 = QtWidgets.QHBoxLayout()
        self.start_date_label = QtWidgets.QLabel("Start:")
        self.start_date_input = QtWidgets.QDateEdit(calendarPopup=True)
        self.start_date_input.setDate(QtCore.QDate.currentDate())
        self.end_date_label = QtWidgets.QLabel("End:")
        self.end_date_input = QtWidgets.QDateEdit(calendarPopup=True)
        self.end_date_input.setDate(QtCore.QDate.currentDate())
        row3.addWidget(self.start_date_label)
        row3.addWidget(self.start_date_input)
        row3.addWidget(self.end_date_label)
        row3.addWidget(self.end_date_input)

        self.id_label = QtWidgets.QLabel("IDs / Emails (any separators):")
        self.id_entry = QtWidgets.QPlainTextEdit()
        self.id_entry.setPlaceholderText("e.g. 12345 67890; a@b.com | c@d.org")
        self.id_entry.textChanged.connect(self._format_ids_vertically)

        row4 = QtWidgets.QHBoxLayout()
        self.run_button = QtWidgets.QPushButton("Run and Export to Excel")
        self.run_button.clicked.connect(self.run_query)
        row4.addWidget(self.run_button)

        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Logs...")

        # Layout stacking
        self.layout.addLayout(row1)
        self.layout.addLayout(row2)
        self.layout.addLayout(row3)
        self.layout.addWidget(self.id_label)
        self.layout.addWidget(self.id_entry)
        self.layout.addLayout(row4)
        self.layout.addWidget(self.log_view)

        # Initial state
        self.toggle_date_fields()
        self._ui_log("GUI ready.")

    # ------------ UI helpers ------------
    def _ui_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log_view.appendPlainText(line)
        logging.info(msg)

    def _format_ids_vertically(self):
        cursor = self.id_entry.textCursor()
        pos = cursor.position()
        ids = self.normalize_ids(self.id_entry.toPlainText())
        self.id_entry.blockSignals(True)
        self.id_entry.setPlainText("\n".join(ids))
        cursor.setPosition(min(pos, len(self.id_entry.toPlainText())))
        self.id_entry.setTextCursor(cursor)
        self.id_entry.blockSignals(False)

    def toggle_date_fields(self):
        ep = self.endpoint_combo.currentText()
        requires_date = ENDPOINTS.get(ep, {}).get("requires_date", False)
        self.start_date_input.setEnabled(requires_date)
        self.end_date_input.setEnabled(requires_date)

    # ------------ Core actions ------------
    def normalize_ids(self, id_text: str) -> List[str]:
        # split on common separators, strip blanks
        parts = re.split(r"[\s,;|]+", id_text.strip())
        return [p.strip() for p in parts if p.strip()]

    def run_query(self):
        endpoint_key = self.endpoint_combo.currentText()
        conf = ENDPOINTS[endpoint_key]
        sites = [it.text() for it in self.site_list.selectedItems()]
        if not sites:
            QtWidgets.QMessageBox.warning(self, "Input", "Please select at least one site.")
            return

        # Dates if needed
        params_date = {}
        if conf.get("requires_date"):
            from_time = to_utc_date_str(self.start_date_input.date(), end_of_day=False)
            to_time = to_utc_date_str(self.end_date_input.date(), end_of_day=True)
            params_date = {"from_time": from_time, "to_time": to_time}
            self._ui_log(f"Date range UTC: {from_time} – {to_time}")

        # IDs / emails
        id_values = self.normalize_ids(self.id_entry.toPlainText())
        id_kind = conf.get("id_kind")  # 'emails' for the email endpoint (UPDATED)
        id_param = conf.get("id_param")  # 'primary_email' for getPersonInfoFullEmail
        batch_size = int(conf.get("batch_size", 25))

        # HTTP session with Digest Auth
        session = requests.Session()
        session.auth = HTTPDigestAuth(API_USERNAME, API_PASSWORD)
        session.headers.update({"Accept": "application/json"})

        url = f"{API_BASE_URL}{conf['path']}"
        all_rows: List[Dict[str, Any]] = []

        # batching
        if id_kind and id_values:
            batches = [id_values[i:i+batch_size] for i in range(0, len(id_values), batch_size)]
        else:
            batches = [[None]]  # allow endpoints without IDs

        for site in sites:
            for batch in batches:
                # Build query params
                q = {"_type": "json", "site_name": site}
                q.update(params_date)

                if id_kind and batch != [None]:
                    # >>> This is the updated logic for email endpoints <<<
                    if id_kind == "emails":
                        pname = id_param or "primary_email"
                        # send one per request
                        value = batch[0] if len(batch) == 1 else batch[0]
                        q[pname] = value
                    else:
                        # fallback: comma-join IDs for other id-based endpoints
                        pname = id_param or "ids"
                        q[pname] = batch[0] if len(batch) == 1 else as_csv(batch)

                # Execute
                self._ui_log(f"🔎 GET {url} {q}")
                try:
                    r = session.get(url, params=q, timeout=60)
                    self._ui_log(f"HTTP {r.status_code}")
                    if r.status_code != 200:
                        self._ui_log(f"Headers: {dict(r.headers)}")
                        body = (r.text or "")[:1000]
                        self._ui_log(f"Body: {body}")
                        continue
                    if not r.text or not r.text.strip():
                        self._ui_log("⚠️ Empty body.")
                        continue
                    data = r.json()
                    rows = flatten_json(data, prefix=site)
                    self._ui_log(f"✅ {site}: +{len(rows)} row(s)")
                    all_rows.extend(rows)
                except Exception as e:
                    self._ui_log(f"❌ {site} error: {type(e).__name__}: {e}")

        if not all_rows:
            self._ui_log("No data to display/export.")
            QtWidgets.QMessageBox.information(self, "No Data", "No records returned.")
            return

        # Export
        df = pd.DataFrame(all_rows)
        outname = f"ScholarOne_API_Export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        try:
            df.to_excel(outname, index=False)
            self._ui_log(f"📄 Wrote {len(df)} rows to {outname}")
            QtWidgets.QMessageBox.information(self, "Success", f"Exported {len(df)} rows to {outname}.")
        except Exception as e:
            self._ui_log(f"❌ Excel write error: {e}")
            QtWidgets.QMessageBox.critical(self, "Excel Error", str(e))


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    logging.info("ScholarOne API GUI starting...")
    app = QtWidgets.QApplication(sys.argv)
    w = ScholarOneAPITool()
    w.show()
    sys.exit(app.exec())
