"""The source audit (reports/audit.py), on the fictional example case and invented notes."""
import pathlib

import pytest

from reports import case as case_mod

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "examples" / "case"


@pytest.fixture
def audit(tmp_path, monkeypatch):
    monkeypatch.setenv("PCR_OUT", str(tmp_path))
    monkeypatch.delenv("PCR_NOTES", raising=False)
    case_mod.load(EXAMPLE)
    from reports import audit as a
    monkeypatch.setattr(a, "C", case_mod.load())
    monkeypatch.setattr(a, "SOURCES", tmp_path / "citations.yaml")
    monkeypatch.setattr(a, "SUGGESTED", tmp_path / "citations.suggested.yaml")
    return a


def note(a, did, text, d="2024-03-05"):
    days, months = a.doc_dates(text)
    return {"id": did, "text": text, "norm": a.norm(text), "days": days, "months": months, "date": d, "type": "oncology", "clinic": ""}


def test_dates_in_notes_and_claims(audit):
    days, months = audit.doc_dates("Seen 3/23/24; CT 2024-03-25; follow-up March 5, 2024; plan 11/2024")
    assert {(2024, 3, 23), (2024, 3, 25), (2024, 3, 5)} <= days and (2024, 11) in months
    assert audit.claim_dates("ICU 6/25–6/28/2025, then ~1/2024") == [(2025, 6, 25), (2025, 6, 28), (2024, 1, None)]


def test_statuses(audit):
    docs = {"n1": note(audit, "n1", "Started capecitabine 1000 mg/m2 twice daily on 8/7/2022 per Dr. Okafor.")}
    c = audit.claim("t/1", "Treatments", "Capecitabine", "Capecitabine 1000 mg/m² twice daily (Dr. Okafor)", [("2022-08-07", False)])
    ok = audit.audit_claim(c, {"src": [{"doc": "n1", "quote": "Started capecitabine 1000 mg/m2"}]}, docs, None)
    assert ok["status"] == "grounded" and not ok["missing"]
    c2 = dict(c, text="Capecitabine 1500 mg twice daily (Dr. Okafor)")
    part = audit.audit_claim(c2, {"src": [{"doc": "n1", "quote": "Started capecitabine"}]}, docs, None)
    assert part["status"] == "partial" and part["missing"] == ["1500 mg"]
    acc = audit.audit_claim(c2, {"src": [{"doc": "n1"}], "accept": {"1500 mg": "dose on the pharmacy label"}}, docs, None)
    assert acc["status"] == "grounded" and acc["accepted"]
    bad = audit.audit_claim(c, {"src": [{"doc": "n1", "quote": "Started letrozole"}]}, docs, None)
    assert bad["status"] == "broken"
    assert audit.audit_claim(c, {"src": [{"doc": "zz"}]}, docs, None)["status"] == "broken"
    assert audit.audit_claim(c, None, docs, None)["status"] == "unsourced"
    assert audit.audit_claim(c, {"src": [{"family": "the family, 10/2026"}]}, docs, None)["status"] == "family"


def test_quote_ignores_line_breaks(audit):
    assert audit.norm_find("Plan:\n  continue   gemcitabine", "Plan: continue gemcitabine") == 0


def test_brand_and_generic_names_match(audit):
    docs = {"n1": note(audit, "n1", "Abraxane (nab-paclitaxel) 100 mg/m2 started 3/15/2024")}
    c = audit.claim("t/2", "Treatments", "nab-Paclitaxel", "nab-Paclitaxel (Abraxane)", [("2024-03-15", False)])
    assert audit.audit_claim(c, {"src": [{"doc": "n1"}]}, docs, None)["status"] == "grounded"


def test_example_claims_and_suggestions(audit):
    keys = {c["key"] for c in audit.all_claims()}
    assert {"event/2025-02-11/hosp", "imaging/2023-05-22", "treatments/4/Sacituzumab govitecan", "emergency/lab/CA 27-29"} <= keys
    audit.suggest(log=lambda *a: None)
    import yaml
    s = yaml.safe_load(audit.SUGGESTED.read_text(encoding="utf-8"))
    src = s["emergency/lab/CA 27-29"]["src"][0]
    assert src["doc"] == "ex00000001" and "9/15/2026" in src["quote"]
    out = audit.run(semantic=False, log=lambda *a: None)
    assert sum(r["status"] == "unsourced" for r in out["claims"]) == len(out["claims"])


def test_not_in_the_records_is_checked_by_search(audit):
    docs = {"n1": note(audit, "n1", "Inpatient Code Status: Full Code"), "n2": note(audit, "n2", "No allergies.")}
    c = audit.claim("q/1", "Open questions", "Code status", "Not documented anywhere in the records.")
    wrong = audit.audit_claim(c, {"src": [{"absent": "code status|advance directive"}]}, docs, None)
    assert wrong["status"] == "broken" and "1 notes match" in wrong["problems"][0]
    right = audit.audit_claim(c, {"src": [{"absent": "living will"}]}, docs, None)
    assert right["status"] == "grounded" and right["searches"][0]["hits"] == []


def test_units_written_with_a_space(audit):
    docs = {"n1": note(audit, "n1", "Prednisolone AC | Ophthalmic Drops 1 % 2gtts 1x daily")}
    c = audit.claim("m/1", "Medications", "Prednisolone", "prednisolone acetate 1% eye drops")
    assert audit.audit_claim(c, {"src": [{"doc": "n1"}]}, docs, None)["status"] == "grounded"


def test_angle_brackets_in_notes_are_kept(audit):
    """Regression (2026-10-21): note text was HTML-stripped, deleting everything between a lab range's "<" and a later ">"."""
    text = "Glucose 98 (Normal is <=99)\nIMPLANT: tibial tray, size 5, uncemented\nCreatinine >0.5"
    docs = {"n1": note(audit, "n1", text)}
    docs["n1"]["norm"] = audit.norm(text, markup=False)
    c = audit.claim("i/1", "Implants", "Tray", "Tibial tray, size 5, uncemented")
    assert audit.audit_claim(c, {"src": [{"doc": "n1", "quote": "tibial tray, size 5"}]}, docs, None)["status"] == "grounded"
