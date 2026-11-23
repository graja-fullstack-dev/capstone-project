import pytest

from pharma_intake.schemas import UpdateStatusArgs
from pharma_intake.validation import find_pii, repair_payload, validate_intake, validate_with


def test_valid_pqc_and_ae(good_pqc, good_ae):
    assert validate_intake(good_pqc).ok
    assert validate_intake(good_ae).ok


@pytest.mark.parametrize("lot", ["LOT-1234", "LOT-123456", "XYZ-12345", "12345"])
def test_bad_lot_rejected_with_explicit_message(good_pqc, lot):
    good_pqc["batch_id"] = lot
    out = validate_intake(good_pqc)
    assert not out.ok and any("LOT-12345" in e and "Batch/Lot" in e for e in out.errors)


def test_missing_mandatory_fields_named(good_pqc):
    del good_pqc["product_name"]
    out = validate_intake(good_pqc)
    assert any("Product name is required" in e for e in out.errors)


def test_ae_requires_event_fields(good_ae):
    del good_ae["event_onset_date"]
    out = validate_intake(good_ae)
    assert any("onset date is required for Suspected Adverse Events" in e for e in out.errors)


def test_pqc_must_not_carry_ae_fields(good_pqc):
    good_pqc.update(event_description="Something happened here", event_onset_date="2026-03-01")
    assert not validate_intake(good_pqc).ok


def test_onset_after_received_and_future_date(good_ae):
    good_ae["event_onset_date"] = "2026-03-05"
    assert not validate_intake(good_ae).ok
    good_ae.update(event_onset_date="2026-03-01", date_received="2999-01-01")
    assert not validate_intake(good_ae).ok


def test_extra_fields_forbidden(good_pqc):
    good_pqc["patient_name"] = "x"
    out = validate_intake(good_pqc)
    assert not out.ok and any("patient_name" in e for e in out.errors)


def test_auto_repair_reports_changes(good_pqc):
    good_pqc.update(batch_id="lot 45210", channel="phone", report_type="pqc")
    out = validate_intake(good_pqc)
    assert out.ok and out.model.batch_id == "LOT-45210"
    assert len(out.repairs) == 3


def test_ref_and_reviewer_repair():
    data, notes = repair_payload({"ref_id": "ref-2026-1", "reviewer_code": "rev 3", "target_status": "close"})
    assert data["ref_id"] == "REF-2026-0001" and data["reviewer_code"] == "REV-03" and data["target_status"] == "Closed"
    assert validate_with(UpdateStatusArgs, data).ok and len(notes) == 3


@pytest.mark.parametrize("text", [
    "Contact jane.doe@example.com for details", "Call 555-123-4567 tomorrow", "Patient name was recorded here",
    "DOB is known to the caller", "lives at 12 Main Street", "MRN noted"])
def test_pii_guard_blocks(good_pqc, text):
    assert find_pii(text)
    good_pqc["description"] = f"Fictional complaint text. {text}"
    assert not validate_intake(good_pqc).ok


def test_pii_guard_allows_codes_and_iso_dates():
    assert not find_pii("LOT-88392 received 2026-03-04 under REF-2026-0001")
