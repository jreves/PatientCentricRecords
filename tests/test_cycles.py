"""The chemotherapy cycles report (reports/cycles.py), on the fictional example case and invented schedules."""
import pathlib

import pytest

from reports import case as case_mod

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "examples" / "case"


@pytest.fixture
def cy(tmp_path, monkeypatch):
    monkeypatch.setenv("PCR_OUT", str(tmp_path))
    monkeypatch.delenv("PCR_NOTES", raising=False)
    case_mod.load(EXAMPLE)
    from reports import cycles
    monkeypatch.setattr(cycles, "C", case_mod.load())
    return cycles


def regimen(cy, **kw):
    r = {"drug": "Testdrug", "schedule": {"length": 28, "days": [1, 8, 15]}, "start": "2026-07-01"} | kw
    return cy.Regimen(r)


def test_cycles_follow_the_schedule_and_a_late_day_1(cy):
    reg = regimen(cy)   # today is 2026-10-01 in the example
    assert [c.start.isoformat() for c in reg.cycles] == ["2026-07-01", "2026-07-29", "2026-08-26", "2026-09-23"]
    assert reg.current().n == 4 and reg.latest_complete().n == 3
    late = regimen(cy, day1=["2026-08-05"])   # cycle 2 started a week late; later cycles follow it
    assert [c.start.isoformat() for c in late.cycles] == ["2026-07-01", "2026-08-05", "2026-09-02", "2026-09-30"]


def test_the_report_tracks_the_last_four_cycles(cy):
    reg = regimen(cy, start="2025-11-05")   # 12 cycles by 10/1/2026
    assert len(reg.cycles) == 12 and [c.n for c in reg.shown] == [9, 10, 11, 12] and reg.shown[-1] is reg.current()
    assert [c.n for c in regimen(cy, start="2025-11-05", show_cycles=2).shown] == [11, 12]
    assert "cycles 1–8" in cy.window_title(reg)
    assert cy.window_title(regimen(cy)).startswith("Every cycle since"), "four or fewer: all of them"


def test_dose_statuses(cy):
    unknown = regimen(cy)
    assert {s for c in unknown.cycles[:3] for _, _, s, _ in c.doses()} == {"not confirmed"}
    assert unknown.cycles[2].status() == "doses not confirmed"
    given = [{"date": d} for d in ("2026-08-26", "2026-09-02", "2026-09-23")]   # cycle 3 day 15 (9/9) has no record
    reg = regimen(cy, infusions=given, infusion_records_from="2026-08-26", not_given=[["2026-09-09", "platelets 60"]])
    c3 = reg.cycles[2]
    assert [(day, s) for day, _, s, _ in c3.doses()] == [(1, "given"), (8, "given"), (15, "not given")]
    assert c3.doses()[2][3] == "platelets 60" and c3.status() == "completed, 2 of 3 doses given"
    assert reg.cycles[0].doses()[0][2] == "not confirmed", "before the records start"
    # the cycle in progress (today 10/1): day 1 given, day 8 (9/30) passed with no record, day 15 expected
    assert [s for _, _, s, _ in reg.cycles[3].doses()] == ["given", "not given", "expected"]
    assert reg.cycles[3].status() == "in progress"


def test_lab_just_before_day_1_is_the_pre_dose_value(cy):
    reg = regimen(cy)
    series = {"2026-06-30": 5.0, "2026-07-08": 2.0, "2026-07-28": 4.0, "2026-07-29": 4.4}
    c1, c2 = reg.cycles[:2]
    assert [(d, v) for d, v, _ in cy.in_cycle(reg, c1, series)] == [(0, 5.0), (8, 2.0), (28, 4.0)]
    assert [(d, v) for d, v, _ in cy.in_cycle(reg, c2, series)] == [(1, 4.4)], "day 1 has its own draw: 7/28 stays in cycle 1"


def test_ctcae_grades(cy):
    assert [cy.grade("ANC", v) for v in (2.0, 1.4, 0.9, 0.4)] == [0, 2, 3, 4]
    assert [cy.grade("PLT", v) for v in (160, 120, 70, 40, 20)] == [0, 1, 2, 3, 4]
    assert cy.grade("HGB", 9.5) == 2 and cy.grade("RBC", 3.0) == 0
    assert [cy.grade("ALT", v) for v in (30, 60, 120, 400)] == [0, 1, 2, 3]


def test_discovery_finds_the_example_regimen(cy):
    out = cy.discover(log=lambda *a: None)
    assert len(out) == 1
    r = out[0]
    assert r["drug"] == "Sacituzumab govitecan" and r["start"] == "2025-10-06" and r["end"] == "@today"
    assert r["schedule"] == {"length": 21, "days": [1, 8]}
    assert [x["date"] for x in r["infusions"]][:2] == ["2026-08-03", "2026-08-10"] and r["infusion_records_from"] == "2026-08-03"
    (cy.C.dir / "cycles.suggested.yaml").unlink()


def test_discovery_patterns(cy):
    import re
    plan, hist = (re.compile(p, re.M) for p in cy.DISCOVERY)
    m = plan.search("Examplemab vedotin-abcd Q21D Cycle Length: 21 Number Cycles: 6 Start: C1D1 on 03/02/2026 Assoc Dx: x")
    assert m and cy._days(m.group("days")) == [1] and m.group("len") == "21"
    m = plan.search("Oralnib (1000 mg/m2) D1-14 Q21D Cycle Length: 21 Start: C1D1 on 01/05/2026")
    assert cy._days(m.group("days")) == list(range(1, 15))
    m = hist.search("===> Weeklytaxel [80 mg/m2; day 1, 8, 15] q28 days: initiated 2/3/2026...")
    assert m.group("drug") == "Weeklytaxel" and cy._days(m.group("days")) == [1, 8, 15]


def test_example_report_builds(cy, tmp_path, monkeypatch):
    monkeypatch.setattr(cy.common, "print_pdf", lambda src, pdf, disclaimer=None: pdf.write_bytes(b"%PDF"))
    cy.main()
    page = (tmp_path / ".work" / "cycles_sacituzumab_govitecan.html").read_text(encoding="utf-8")
    assert "cycle 16, 8/24/2026" in page and "Infusion records start 8/3/2026" in page
    assert "held for ANC 0.9" in page and "family report" in page and "Cycle 18 day 1: 10/5/2026" in page
