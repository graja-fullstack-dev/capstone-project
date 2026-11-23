import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pharma_intake import db  # noqa: E402


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")  # never touches logs/app.db
    yield c
    c.close()


GOOD_PQC = {
    "report_type": "Product Quality Complaint", "product_name": "Fictazol 10 mg Tablets", "batch_id": "LOT-45210",
    "date_received": "2026-03-04", "reporter_type": "Consumer", "channel": "Email",
    "description": "Fictional complaint: blister strip had discolored tablets and one was cracked.",
}
GOOD_AE = {
    **GOOD_PQC, "report_type": "Suspected Adverse Event", "batch_id": "LOT-88392",
    "description": "Fictional case: reporter described mild nausea after starting the product.",
    "event_description": "Mild nausea reported after starting the product.", "event_onset_date": "2026-03-02",
}


@pytest.fixture
def good_pqc():
    return dict(GOOD_PQC)


@pytest.fixture
def good_ae():
    return dict(GOOD_AE)
