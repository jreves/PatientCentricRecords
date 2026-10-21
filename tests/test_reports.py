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
    assert used == 8 and data["WBC"]["2026-09-16"] == 3.9 and data["ANC"]["2025-11-17"] == 0.8


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
