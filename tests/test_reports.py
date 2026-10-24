"""The report engine on the fictional example case (examples/case). HTML only, so no browser is needed."""
import pathlib

import pytest

from reports import case as case_mod

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "examples" / "case"


@pytest.fixture
def example(tmp_path, monkeypatch):
    monkeypatch.setenv("PCR_OUT", str(tmp_path))
    monkeypatch.delenv("PCR_NOTES", raising=False)
    return case_mod.load(EXAMPLE)


def test_example_reads_only_its_own_notes(example):
    assert example.notes == EXAMPLE / "notes"
    from reports import labs
    data, used = labs.parse()
    assert used == 11 and data["WBC"]["2026-09-14"] == 5.2 and data["ANC"]["2025-11-17"] == 0.8
    chem, _ = labs.parse({"ALT": [r"ALT/SGPT", r"U/L"], "RBC": r"RBC\b"})   # rows with their own unit, and the default unit
    assert chem["ALT"]["2026-08-10"] == 41 and chem["RBC"]["2026-08-31"] == 3.7


def test_lab_values_from_ccda_result_rows(example, tmp_path, monkeypatch):
    """2026-10-24: visit summaries (C-CDA) list results one per row, with the date; they fill dates the visit-note lab
    tables don't have. The unit is checked, so a urine WBC isn't read as a blood count."""
    from reports import labs
    (tmp_path / "n").mkdir()
    (tmp_path / "n" / "2026-03-02_outpatient-visit_ab12cd34ef.md").write_text(
        "RESULTS\nGroup | Component | Quantity | Performed\n"
        "CBC w/auto diff | WBC 10^3/uL ( 4.8 - 10.8 10^3/uL ) | 3.9 | 2026-03-02\n"
        "CBC w/auto diff | Neu # (ANC) 10^3/?l ( 1.5 - 6.5 10^3/?l ) | 1.2 | 2026-03-02\n"
        "CMP | ALT/SGPT U/L ( 14.0 - 59.0 U/L ) | 61 | 2026-03-02\n"
        "Urinalysis | WBC /HPF ( 0 - 5 /HPF ) | 12 | 2026-03-02\n", encoding="utf-8")
    monkeypatch.setattr(labs, "notes", lambda: tmp_path / "n")
    d, used = labs.parse({"WBC": r"WBC\b", "ANC": r"Neu # \(ANC\)", "ALT": [r"ALT/SGPT", r"U/L"]})
    assert used == 1 and d == {"WBC": {"2026-03-02": 3.9}, "ANC": {"2026-03-02": 1.2}, "ALT": {"2026-03-02": 61.0}}


def test_yaml_dates_and_today_resolved(example):
    assert example["tumor_marker"]["values"][0][0] == "2021-03-10"
    current = example["therapy_groups"]["systemic"][-1]
    assert current["end"] == example.today == "2026-10-01"


def test_example_timeline_page(example, tmp_path):
    from reports import timeline
    cfgs = timeline.charts()
    cancer = cfgs["cancer"]
    assert len(cancer["bars"]) == 10 and len(cancer["line"]["points"]) == 15
    # every hospital event and imaging study becomes a marker, plus the side effects
    assert len(cancer["markers"]) == 4 + 1 + 9 + 3
    timeline.build_pages(cfgs)
    page = (tmp_path / "cancer_timeline.html").read_text(encoding="utf-8")
    assert "Sacituzumab govitecan" in page and "Patient identifiers removed" in page
