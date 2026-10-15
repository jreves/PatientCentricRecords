"""Regression tests on synthetic notes. All identifiers here are invented.

Run: python -m pytest -q
"""
import pathlib
from datetime import date

import pytest

from pipeline import chrono
from pipeline.config import Paths
from pipeline.core import run
from pipeline.names import parse_name

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

IDENTIFIERS = """
[patient]
names = ["Margaret Ann Thornbury"]
dob = "1961-04-12"
ids = ["00473921"]
phones = ["555-555-0144"]
addresses = ["2200 Sunrise Rd, Fairview, TX 78990"]

[people]
names = ["Dale Thornbury"]
"""
LEAKS = ["Thornbury", "THORNBURY", "Margaret", "MARGARET", "Kulkarni", "Rajesh", "Chen", "Dale", "Oyelaran",
         "Susan", "04/12/1961", "00473921", "A[ID]", "555-0144", "Sunrise", "A99812734", "S06-44821"]
KEEP = ["letrozole", "palbociclib", "HER2", "Herceptin", "03/14/2011", "invasive ductal carcinoma", "CA 27-29"]


def run_synthetic(tmp_path, policy):
    private = tmp_path / "private"
    private.mkdir()
    (private / "identifiers.toml").write_text(IDENTIFIERS, encoding="utf-8")
    cfg = {"sources": [{"name": "synthetic", "path": "synthetic"}], "output": {"dir": "out"},
           "llm": {"enabled": False}, "policy": policy, "allowlist": {"terms": ["MD Anderson"]}}
    paths = Paths(FIXTURES, private, tmp_path / "out")
    published = run(cfg, paths, use_llm=False, log=lambda *a, **k: None)
    assert not published, "a run without the LLM must never publish"
    return {p.name: p.read_text(encoding="utf-8") for p in (paths.staging / "notes").glob("*.md")}


@pytest.fixture
def staged(tmp_path):
    """Strictest policy: clinicians and facilities pseudonymized too."""
    return run_synthetic(tmp_path, {})


PATIENT_LEAKS = ["Thornbury", "THORNBURY", "Margaret", "MARGARET", "Dale", "04/12/1961", "00473921", "555-0144",
                 "Sunrise", "A99812734", "S06-44821"]


def test_clinicians_kept_patient_protected(tmp_path):
    """Current policy (2026-09-23): clinician names stay, the patient and family do not."""
    text = "\n".join(run_synthetic(tmp_path, {"redact_clinicians": False, "redact_facilities": False}).values())
    for kept in ["Provider: Rajesh Kulkarni, MD", "Dr. Chen", "Follow up with Kulkarni", "Susan Oyelaran, MD",
                 "Copy to: Dr. Kulkarni"]:
        assert kept in text, f"clinician name should be kept: {kept}"
    for leak in PATIENT_LEAKS:
        assert leak not in text, f"leaked: {leak}"
    assert "Ms. [PATIENT]" in text and "husband [PERSON-" in text


def test_relatives_never_classed_as_clinicians(tmp_path):
    """Even if every detector calls them clinicians, relatives sharing her surname and
    user-listed people stay PERSON, because clinician names are published."""
    from pipeline.names import Allowlist, Registry
    reg = Registry(tmp_path / "registry.json")
    ids = {"patient": {"names": ["Margaret Thornbury"]}, "people": {"names": ["Jo Smith"]}}
    mentions = [("Dale Thornbury", "CLINICIAN")] * 3 + [("Jo Smith, MD", "CLINICIAN")] * 3 \
        + [("Ann Lee", "CLINICIAN"), ("Ann Lee", "PERSON"), ("Raj Rao, MD", "CLINICIAN")]
    reg.build(mentions, ids, Allowlist({}))
    cats = {tuple(e["names"][0]): e["cat"] for e in reg.entities if e["id"] != "PATIENT"}
    assert cats[("dale", "thornbury")] == "PERSON"
    assert cats[("jo", "smith")] == "PERSON"
    assert cats[("ann", "lee")] == "PERSON", "a tie must not publish the name"
    assert cats[("raj", "rao")] == "CLINICIAN"


def test_no_known_identifiers_survive(staged):
    text = "\n".join(staged.values())
    for leak in LEAKS:
        assert leak not in text, f"leaked: {leak}"


def test_clinical_content_kept(staged):
    text = "\n".join(staged.values())
    for term in KEEP:
        assert term in text, f"over-redacted: {term}"


def test_chronological_names_and_dates(staged):
    names = sorted(staged)
    assert names[0].startswith("2006-05-02_pathology_")
    assert names[1].startswith("2011-03-14_")


def test_pseudonyms_are_consistent(staged):
    progress = next(v for k, v in staged.items() if k.startswith("2011"))
    assert "Provider: [CLINICIAN-" in progress
    token = progress.split("Provider: ")[1].split("]")[0] + "]"
    assert f"Follow up with {token}" in progress, "bare surname must map to the same clinician"
    assert "Ms. [PATIENT]" in progress and "[PATIENT], MD" not in progress
    assert "husband [PERSON-" in progress


def test_dob_dropped_age_kept(staged):
    progress = next(v for k, v in staged.items() if k.startswith("2011"))
    pathology = next(v for k, v in staged.items() if k.startswith("2006"))
    assert "DOB: [DOB; age 49]" in progress
    assert "patient_age: 49" in progress
    assert "49 yo woman" in progress, "stated ages must survive"
    assert "patient_age: 45" in pathology, "age comes from identifiers.toml DOB when the note has none"


def test_age_at():
    assert chrono.age_at(date(1961, 4, 12), date(2011, 4, 11)) == "49"
    assert chrono.age_at(date(1961, 4, 12), date(2011, 4, 12)) == "50"
    assert chrono.age_at(date(1920, 1, 1), date(2015, 1, 1)) == "90+"
    assert chrono.age_at(None, date(2011, 1, 1)) is None


def test_parse_name():
    assert parse_name("Rajesh Kulkarni, MD") == ("rajesh", "kulkarni", None)
    assert parse_name("THORNBURY, MARGARET A") == ("margaret", "thornbury", None)
    assert parse_name("Dr. Chen") == (None, "chen", "dr")
    assert parse_name("Nurse Practitioner") is None


@pytest.mark.parametrize("s,expected", [
    ("03/14/2011", date(2011, 3, 14)), ("3/4/11", date(2011, 3, 4)), ("2011-03-14", date(2011, 3, 14)),
    ("March 14, 2011", date(2011, 3, 14)), ("14-Mar-2011", date(2011, 3, 14)), ("13/45/2011", None)])
def test_parse_date(s, expected):
    assert chrono.parse_date(s) == expected


def test_verify_ignores_tokens_and_label_words(tmp_path):
    """Regression (2026-09-23): a junk entity named "ID" matched inside our own [ID] tokens."""
    import json
    from pipeline.names import Allowlist
    from pipeline.verify import verify_texts
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps({"entities": [{"id": "CLINICIAN-01", "cat": "CLINICIAN", "names": [[None, "id"]],
                                             "aliases": [], "surfaces": ["ID"]}], "orgs": [], "counters": {}}))
    fails, _ = verify_texts({"d": "Patient: [PATIENT] MRN: [ID] DOB: [DOB; age 49]"}, {}, reg, Allowlist({}))
    assert fails == []
    assert parse_name("ID") is None and parse_name("MRN") is None


def test_credential_stack_is_not_a_name(tmp_path):
    """Regression (2026-09-23): "MSN, RN FNP-C" after a redacted name was flagged as a name."""
    from pipeline.names import Allowlist
    from pipeline.verify import verify_texts
    text = "Signed: [CLINICIAN-01] MSN, RN FNP-C\nCopy: LEE, JO FNP-C"
    _, warns = verify_texts({"d": text}, {}, tmp_path / "none.json", Allowlist({}))
    assert [w[2] for w in warns] == ["LEE, JO FNP-C"], "real names must still warn"


def test_drug_names_and_lowercase_words_are_not_people(tmp_path):
    """Regression (2026-09-23): the LLM tagged drug brand names and plain words as person names."""
    from pipeline.core import locate_llm
    from pipeline.names import Allowlist, Registry
    allow = Allowlist({})
    text = "Started Ibrance 125 mg with letrozole (Femara). Husband Dale present. Xeloda held."
    ents = [("Ibrance", "PERSON"), ("Femara", "PERSON"), ("Xeloda 1000", "PERSON"), ("letrozole", "PERSON"),
            ("Dale", "PERSON")]
    spans, _ = locate_llm(text, ents, allow)
    assert [text[s.start:s.end] for s in spans] == ["Dale"]
    reg = Registry(tmp_path / "r.json")
    reg.entities = [{"id": "PERSON-01", "cat": "PERSON", "names": [[None, "verzenio"]], "aliases": [], "surfaces": ["Verzenio"]},
                    {"id": "PERSON-02", "cat": "PERSON", "names": [[None, "sometimes"]], "aliases": [], "surfaces": ["sometimes"]},
                    {"id": "PERSON-03", "cat": "PERSON", "names": [[None, "dale"]], "aliases": [], "surfaces": ["Dale"]}]
    reg._reindex()   # entities assigned directly (normally loaded from the registry file)
    reg.build([("Dale", "PERSON"), ("Verzenio", "PERSON")], {}, allow)
    assert [e["id"] for e in reg.entities] == ["PERSON-03"], "junk entities must be pruned"


def test_llm_category_sanity_and_term_exemptions(tmp_path):
    """Regression (2026-09-23): drug names labelled PHONE/EMAIL/URL were redacted as [PHONE]."""
    from pipeline.core import locate_llm, sanity_check
    from pipeline.names import Allowlist
    assert sanity_check("Ondansetron", "PHONE") is None
    assert sanity_check("(555) 555-0144", "PHONE") == "PHONE"
    assert sanity_check("Vitamin D", "ID") is None
    allow = Allowlist({})
    assert allow.blocks("Femara 2.5 mg") and allow.blocks("Tempus xT") and allow.blocks("Kisqali-Femara")
    assert not allow.blocks("Jane Caris"), "a real-looking name that shares a term's spelling stays redacted"
    text = "Ondansetron 8 mg prn. Wife Jane Caris called."
    spans, _ = locate_llm(text, [("Ondansetron", "PHONE"), ("Jane Caris", "PERSON")], allow)
    assert [text[s.start:s.end] for s in spans] == ["Jane Caris"]


def test_stale_registry_entities_are_dropped(tmp_path):
    from pipeline.names import Allowlist, Registry
    reg = Registry(tmp_path / "r.json")
    reg.build([("Ann Lee", "PERSON"), ("Bo Chu", "PERSON")], {}, Allowlist({}))
    ids = {e["names"][0][1]: e["id"] for e in reg.entities}
    reg.save()
    reg = Registry(tmp_path / "r.json")
    reg.build([("Bo Chu", "PERSON")], {}, Allowlist({}))
    assert [(e["names"][0][1], e["id"]) for e in reg.entities] == [("chu", ids["chu"])], "stable id, stale entity gone"


def test_multiword_terms_match_partial_and_reordered_surfaces():
    """Regression (2026-09-24): user entries like "X-Y Topical Cream" missed "X-Y" and "Y X"."""
    from pipeline.names import Allowlist
    allow = Allowlist({"allowlist": {"terms": ["Zorbex-Quilane Topical Cream"]}})
    assert allow.blocks("Zorbex-Quilane") and allow.blocks("Quilane Zorbex 2.5%") and allow.blocks("Topical Cream")
    assert not allow.blocks("Jane Zorbex"), "a term word beside a non-term word stays redacted"


def test_patient_geography_redacted_but_not_credentials_or_labs():
    """2026-09-24: hometown / prior residence ("City, ST") is patient information."""
    from pipeline import rules
    rx = dict((n, r) for n, r, _ in rules.PATTERN_RULES)["city-state"]
    assert [m.group("v") for m in rx.finditer("originally from Springville, Tx. Seen in Lakeview, Colorado")] == \
        ["Springville, Tx", "Lakeview, Colorado"]
    for text in ["Rajesh Kulkarni, MD", "Lee, PA-C", "CEA, CA 27-29 rising", "Mg, Ca, Phos", "BUN, CO2 24", "Smith, In"]:
        assert not rx.search(text), text


def test_visit_types_for_oncology_template():
    t = chrono.note_type
    assert t(["Lakeside Oncology Palliative Care\nHistory of Present Illness:\npresents for initial consultation"]) \
        == "palliative-care-consult"
    assert t(["Oncology Clinic\nSYMPTOM MANAGEMENT:\nPain"]) == "palliative-care-follow-up"
    assert t(["Lakeside Oncology Palliative Care\npresents for initial consultation (carried forward)\n"
              "X is a 68-year-old presenting for follow-up"]) == "palliative-care-follow-up"
    assert t(["FOLLOW-UP NOTE\nCHIEF COMPLAINT: ... status post palliative radiotherapy"]) == "radiation-oncology-follow-up"
    assert t(["History of Present Illness:\nhere for treatment review and coordination of care"]) == "treatment-review"
    assert t(["History of Present Illness:\nreturns for follow-up\nInterval History:"]) == "oncology-follow-up"
    assert t(["SURGICAL PATHOLOGY REPORT\nFINAL DIAGNOSIS"]) == "pathology", "generic fallback for other sources"
    assert chrono.clinic(["Lakeside Oncology Millbrook\n[ADDRESS]"]) == "Lakeside Oncology Millbrook"


def _write_docx(path, paragraphs, table_rows):
    import zipfile
    from xml.sax.saxutils import escape
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    p = "".join(f"<w:p><w:r><w:t>{escape(t)}</w:t></w:r></w:p>" for t in paragraphs)
    rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{escape(c)}</w:t></w:r></w:p></w:tc>" for c in r)
                   + "</w:tr>" for r in table_rows)
    xml = f'<?xml version="1.0"?><w:document {W}><w:body>{p}<w:tbl>{rows}</w:tbl></w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


def test_docx_and_xlsx_sources(tmp_path):
    """2026-09-25: new sources include Word and Excel files."""
    import datetime
    import openpyxl
    src = tmp_path / "src"
    src.mkdir()
    _write_docx(src / "summary.docx", ["Patient: Margaret Thornbury", "Date of Surgery: 05/09/2021",
                                       "OPERATIVE REPORT", "Right hip replacement. Husband Dale at bedside."],
                [["Procedure", "Surgeon"], ["Hip revision", "Dr. Chen"]])
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Date", "CA 27-29", "CA 15-3", "CEA"])
    for i, v in enumerate([88, 95, 120]):
        ws.append([datetime.datetime(2023, 1 + i, 15), v, v / 2, 2.5])
    ws.cell(row=1, column=40, value=None)   # inflated used range, like the real surgical sheet
    wb.save(src / "markers.xlsx")
    private = tmp_path / "private"
    private.mkdir()
    (private / "identifiers.toml").write_text(IDENTIFIERS, encoding="utf-8")
    cfg = {"sources": [{"name": "extra", "path": "src"}], "output": {"dir": "out"}, "llm": {"enabled": False},
           "policy": {"redact_clinicians": False, "redact_facilities": False}, "allowlist": {"terms": []}}
    paths = Paths(tmp_path, private, tmp_path / "out")
    run(cfg, paths, use_llm=False, log=lambda *a, **k: None)
    notes = {p.name: p.read_text(encoding="utf-8") for p in (paths.staging / "notes").glob("*.md")}
    docx = next(v for k, v in notes.items() if "operative" in k)
    xlsx = next(v for k, v in notes.items() if "spreadsheet" in k)
    assert "Thornbury" not in docx and "Dale" not in docx and "Hip revision | Dr. Chen" in docx
    assert "date: 2021-05-09" in docx and "format: docx" in docx
    assert "2023-01-15 | 88 | 44 | 2.5" in xlsx and "date: 2023-01-15" in xlsx
    assert "spreadsheet rows dated 2023-01-15 to 2023-03-15" in xlsx


def test_address_lines_without_street_suffix_or_with_9_digit_zip():
    """Regression (2026-09-25): a hospital 'Patient Information' block leaked a home address:
    no street suffix, 9-digit ZIP without a dash."""
    from pipeline import rules
    denylist = rules.Denylist({})
    text = ("Patient Information:\n123 Sunset Bend Springville, TX 786401234\n"
            "Mailing: 45 Oak Hollow Lakeview, Texas 78640\nCA 27-29 was 88, CA 125 normal, CEA, CA 15-3 stable")
    spans = rules.detect(text, denylist)
    covered = set()
    for s in spans:
        if s.cat in ("ADDRESS", "LOCATION"):
            covered.update(range(s.start, s.end))
    leftover = "".join(ch if i not in covered else "#" for i, ch in enumerate(text))
    for leak in ["123", "Sunset", "Springville", "786401234", "45 Oak", "Lakeview", "78640"]:
        assert leak not in leftover, f"leaked: {leak}"
    for kept in ["CA 27-29", "CA 125", "CA 15-3"]:
        assert kept in leftover, f"over-redacted: {kept}"


def _epic_page(section, body, continued=True):
    head = ("Mercy General Hospital Margaret Thornbury\n100 Test Way MRN: 00473921, DOB: 04/12/1961, Sex: F\n"
            "100 Test Way Adm: 6/12/2023, D/C: 6/14/2023\n"
            "06/12/2023 - ED to Hosp-Admission (Discharged) in Mercy General Med Surg (continued)\n")
    return head + section + (" (continued)" if continued else "") + "\n" + body


def test_epic_encounter_export_is_split_into_sections(tmp_path):
    """2026-09-26: hospital encounter exports (hundreds of pages) become one document per section."""
    src = tmp_path / "src"
    src.mkdir()
    pages = [_epic_page("FACESHEET", "Guarantor: self\nRegistration details", continued=False)]
    pages += [_epic_page("FACESHEET", "More registration\n\nH&P Notes\nDate of Service: 06/12/2023\n"
                                      "HPI: 66F with metastatic breast cancer and hip dislocation.")]
    pages += [_epic_page("H&P Notes", "Plan: revision arthroplasty. Seen by Dr. Chen.")]
    pages += [_epic_page("H&P Notes", "Exam unremarkable.\nDischarge Summary Note\nDischarged 6/14/2023 on enoxaparin.")]
    pages += [_epic_page("Discharge Summary Note", "Follow up with orthopedics in 2 weeks.")]
    pages += [_epic_page("Other Orders (group 1 of 2)", f"Order {i}: CBC daily") for i in range(5)]
    pages += [_epic_page("Flowsheets", "Vitals q4h", continued=False)] * 2
    (src / "export.txt").write_text("\f".join(pages), encoding="utf-8")
    private = tmp_path / "private"
    private.mkdir()
    (private / "identifiers.toml").write_text(IDENTIFIERS, encoding="utf-8")
    cfg = {"sources": [{"name": "hospital", "path": "src"}], "output": {"dir": "out"}, "llm": {"enabled": False},
           "policy": {"redact_clinicians": False, "redact_facilities": False}, "allowlist": {"terms": []}}
    paths = Paths(tmp_path, private, tmp_path / "out")
    run(cfg, paths, use_llm=False, log=lambda *a, **k: None)
    notes = {p.name: p.read_text(encoding="utf-8") for p in (paths.staging / "notes").glob("*.md")}
    types = sorted(k.split("_")[1] for k in notes)
    assert types == ["discharge-summary", "encounter-admin", "flowsheets", "hospital-h&p", "orders"], types
    hp = next(v for k, v in notes.items() if "hospital-h&p" in k)
    assert "HPI: 66F" in hp and "revision arthroplasty" in hp, "the section starts mid-page 2"
    assert "Discharged 6/14/2023" not in hp, "the next section starts mid-page 4"
    assert "date: 2023-06-12" in hp and "section: \"H&P Notes\"" in hp and "clinical: true" in hp
    assert "Thornbury" not in "".join(notes.values()) and "00473921" not in "".join(notes.values())
    combined = (paths.staging / "all_notes_chronological.md").read_text(encoding="utf-8")
    assert "revision arthroplasty" in combined and "CBC daily" not in combined, "orders stay out of the clinical file"
    assert "CBC daily" in (paths.staging / "all_documents_chronological.md").read_text(encoding="utf-8")


def test_hospital_export_formats_are_dated_and_typed():
    h = chrono.hospital_format
    assert h(["X Admin Sex: Female\nInpatient Summary\nSummarization of Episode Note | 05/9/2021 to 05/13/2021"]) == \
        (date(2021, 5, 9), "episode 05/9/2021 to 05/13/2021", "inpatient-summary")
    assert h(["2/5/25, 8:10 AM Full Encounter Summary\nPatient\n[PATIENT] (64yo, F) Appt.\nName 06/29/2022 02:00PM"]) == \
        (date(2022, 6, 29), "appointment 06/29/2022", "outpatient-visit")
    assert h(["4/12/24, 1:45 PM Portal - Hospital Admissions\nNote From Your Admission on 03/23/24\n"
              "Op Note by Alan Fictus, MD at 5/14/2023 4:10 PM"])[2] == "operative"
    assert h(["Portal\nED Provider Notes\nJane Roe, MD at 6/11/2023 8:06 PM"])[:2] == \
        (date(2023, 6, 11), "ed-provider-note dated 6/11/2023")
    assert h(["Lakeside Oncology Millbrook\nDate of Service: 02/21/2022"]) is None


def test_ids_found_anywhere_are_redacted_everywhere(tmp_path):
    """Regression (2026-09-26): a patient ID printed unlabelled leaked; the same ID was labelled elsewhere."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("Full Encounter Summary\nID# 420802 Date/Time\nChief Complaint: pain", encoding="utf-8")
    (src / "b.txt").write_text("Visit note. Reference 420802 in the practice system.", encoding="utf-8")
    private = tmp_path / "private"
    private.mkdir()
    cfg = {"sources": [{"name": "s", "path": "src"}], "output": {"dir": "out"}, "llm": {"enabled": False},
           "policy": {}, "allowlist": {"terms": []}}
    paths = Paths(tmp_path, private, tmp_path / "out")
    run(cfg, paths, use_llm=False, log=lambda *a, **k: None)
    assert "420802" not in "".join(p.read_text(encoding="utf-8") for p in (paths.staging / "notes").glob("*.md"))


def test_textless_pages_dropped_by_policy(tmp_path):
    from pipeline.core import describe, drop_textless
    from pipeline.extract import Document
    from collections import Counter
    doc = Document("abc", "s", "f.pdf", ["", "Date of Service: 01/02/2024\nReal note text here " * 3], "pdf")
    entries = drop_textless(describe(doc, doc.pages, [Counter(), Counter()], None), doc)
    assert [e["page_numbers"] for e in entries] == [[2]]
    only_scans = Document("def", "s", "g.pdf", ["", " "], "pdf")
    assert drop_textless(describe(only_scans, only_scans.pages, [Counter(), Counter()], None), only_scans) == []


CCDA = FIXTURES / "ccda" / "episode.xml"


def test_ccda_header_allowlist_and_sections():
    """2026-09-27: C-CDA XML reader emits only allowlisted header fields and drops insurance/care team."""
    from pipeline import ccda
    pages = ccda.read(CCDA)
    text = "\n".join(pages)
    for leak in ["Thornbury", "Margaret", "00473921", "Sunrise", "555-0144", "19610412", "Dale", "W123456789",
                 "Author Way", "555-9999"]:
        assert leak not in text, f"header/insurance/care-team content leaked: {leak}"
    assert pages[0].splitlines()[:3] == ["Inpatient Summary", "C-CDA: Summarization of Episode Note | 11/18/2024 to 11/18/2024",
                                          "Source: Mercy General Hospital"]
    assert "Hemoglobin | 10.2 g/dL | 12.0-16.0" in text, "tables become rows"
    assert "No data available" not in text, "empty sections are skipped"
    assert chrono.hospital_format(pages) == (date(2024, 11, 18), "episode 11/18/2024 to 11/18/2024", "inpatient-summary")


def test_duplicate_detection_prefers_xml_and_respects_dates():
    from pipeline import ccda
    from pipeline.dedup import find_duplicates
    from pipeline.extract import Document
    xml = Document("x1", "h", "a.xml", ccda.read(CCDA), "xml")
    # the same episode "printed": same words, different layout and page breaks, plus a print header
    printed = Document("p1", "h", "a.pdf", ["Printed 9/27/2026 page 1 of 2\n" + "\n".join(xml.pages[:2]),
                                             "\n".join(xml.pages[2:])], "pdf")
    # another visit built from the same template, on a different date
    other = Document("p2", "h", "b.pdf", [p.replace("11/18/2024", "12/02/2024") for p in printed.pages], "pdf")
    kept, dropped = find_duplicates([printed, xml, other])
    assert [d.doc_id for d in kept] == ["x1", "p2"], "XML kept over its PDF twin; different-date visit kept"
    assert [(a, b) for a, b, _ in dropped] == [("p1", "x1")]
    unrelated = Document("u1", "h", "c.txt", ["Oncology follow-up. Date of Service: 01/02/2024. Stable disease."], "txt")
    assert len(find_duplicates([xml, unrelated])[0]) == 2


def test_short_sections_kept_and_episode_twins_merged():
    """Regression (2026-09-27): a short 'Reason for Visit' was skipped; an XML and its PDF printout with the
    same episode dates but different wording must be one document (XML kept)."""
    from pipeline import ccda
    from pipeline.dedup import find_duplicates
    from pipeline.extract import Document
    pages = ccda.read(CCDA)
    assert any(p.startswith("Reason for Visit\nUpper back pain") for p in pages)
    xml = Document("x1", "h", "a.xml", pages, "xml")
    pdf = Document("p1", "s", "a.pdf", ["Inpatient Summary\nSummarization of Episode Note | 11/18/2024 to 11/18/2024\n"
                                         "Goals\nNo data available for this section\nImmunizations\nNo data available\n"
                                         "Family History\nNo data available for this section\nReason for Visit\nUpper back pain"], "pdf")
    kept, dropped = find_duplicates([pdf, xml])
    assert [d.doc_id for d in kept] == ["x1"] and dropped[0][:2] == ("p1", "x1")
    other = Document("p2", "s", "b.pdf", [pdf.pages[0].replace("11/18/2024 to 11/18/2024", "11/18/2024 to 11/20/2024")], "pdf")
    assert len(find_duplicates([other, xml])[0]) == 2, "different episode end date: a different stay"


def test_table_rows_on_separate_lines_and_long_lines_chunked(tmp_path):
    """Regression (2026-09-27): all rows of an XML table landed on one 4.7k-char line; the LLM chunk overflowed."""
    from pipeline import ccda
    from pipeline.llm import OllamaNER
    text = "\n".join(ccda.read(CCDA))
    assert "Test | Result | Range\nHemoglobin | 10.2 g/dL | 12.0-16.0\nPlatelets | 145 K/uL | 150-400" in text
    ner = OllamaNER({"url": "http://localhost:0", "model": "m", "max_chunk_chars": 400}, tmp_path)
    long_line = " | ".join(f"cell{i} value{i}" for i in range(200))
    chunks = list(ner._chunks(long_line))
    assert len(chunks) > 1 and all(len(c) <= 400 for c in chunks)
    assert "".join(chunks).replace(" | ", "").replace("\n", "") == long_line.replace(" | ", "")


def test_fuzzy_catches_ocr_garbled_identifiers(tmp_path):
    """2026-09-27: OCR misreads defeat exact matching; OCR'd documents get fuzzy identifier matching."""
    from pipeline import fuzzy
    from pipeline.names import Allowlist, Registry
    reg = Registry(tmp_path / "r.json")
    reg.build([("Margaret Thornbury", "PATIENT"), ("Dale Thornbury", "PERSON"), ("Rajesh Kulkarni, MD", "CLINICIAN")] * 2,
              {"patient": {"names": ["Margaret Thornbury"]}, "people": {"names": ["Dale Thornbury"]}}, Allowlist({}))
    targets = fuzzy.name_targets(reg, kept_cats={"CLINICIAN"})
    text = "Pt Th0rnbury, Margarel seen with husband Da1e. Dr. Kulkami reviewed. Thornberry follow-up. Market day."
    hits = {text[s:e] for s, e, _, _ in fuzzy.name_hits(text, targets)}
    assert {"Th0rnbury", "Margarel", "Thornberry"} <= hits, hits
    assert "Da1e" in hits, "4-letter names match exactly after undoing OCR swaps (1->l)"
    assert "Kulkami" not in hits, "clinicians are kept, so they aren't fuzzy targets"
    assert "Market" not in hits and "day" not in hits, "ordinary words are not names"
    digits = fuzzy.digit_targets({"patient": {"dob": "1961-04-12", "ids": ["00473921"], "phones": ["555-555-0144"]}})
    nt = "DOB: O4/l2/1961  MRN OO473921  call (555) 555-Ol44  Hgb 10.2"
    got = {nt[s:e].strip() for s, e, _, _ in fuzzy.number_hits(nt, digits)}
    assert any("O4/l2/1961" in g for g in got) and any("OO473921" in g for g in got) and any("555-Ol44" in g for g in got), got
    assert not any("10.2" in g for g in got)


def test_fuzzy_spares_clinician_full_name_near_a_family_name(tmp_path):
    """2026-09-28: an OCR'd referring oncologist's surname was one edit from a family name part and became
    [PATIENT]. Written beside the rest of a known clinician's name it is the clinician; alone, or an exact
    family-name match, it is still a hit."""
    from pipeline import fuzzy
    from pipeline.names import Allowlist, Registry
    reg = Registry(tmp_path / "r.json")
    reg.build([("Margaret Thornbury", "PATIENT"), ("Nora Wendt", "PERSON"), ("Ellen Wend, MD", "CLINICIAN")] * 2,
              {"patient": {"names": ["Margaret Thornbury"]}, "people": {"names": ["Nora Wendt"]}}, Allowlist({}))
    targets = fuzzy.name_targets(reg, kept_cats={"CLINICIAN"})
    clin = fuzzy.clinician_names(reg)
    text = ("Referring Provider: WEND, ELLEN\nPatient Age: 61 ELLEN WEND MD\nSister Wend visited. Wendt called.\n"
            "Visitors: Ellen Wend and family")
    hits = [text[s:e] for s, e, _, _ in fuzzy.name_hits(text, targets, clin)]
    assert hits == ["Wend", "Wendt", "Wend"], "the full name counts as the clinician only with a credential, title or provider label"
    assert [text[s:e] for s, e, _, _ in fuzzy.name_hits(text, targets)].count("WEND") == 2, "no exemption without the clinician list"


def test_tesseract_ocr_roundtrip(tmp_path):
    """Integration: render a synthetic scanned page, OCR it through the pipeline's OCR class."""
    import shutil
    from PIL import Image, ImageDraw, ImageFont
    from pipeline.ocr import OCR, OCRError
    try:
        ocr = OCR({}, tmp_path / "cache")
    except OCRError:
        pytest.skip("Tesseract not installed")
    img = Image.new("RGB", (2550, 900), "white")
    try:
        font = ImageFont.truetype("arial.ttf", 64)
    except OSError:
        pytest.skip("no TrueType font for the synthetic scan")
    ImageDraw.Draw(img).multiline_text((120, 150), "OPERATIVE REPORT\nDate of Surgery: 03/14/2011\nLeft mastectomy performed.", fill="black", font=font, spacing=40)
    pdf = tmp_path / "scan.pdf"
    img.save(pdf, "PDF", resolution=300)
    text, conf = ocr.page(pdf.read_bytes(), "a" * 64, 0)
    assert "OPERATIVE REPORT" in text and "03/14/2011" in text and "mastectomy" in text
    assert conf > 80
    assert ocr.page(pdf.read_bytes(), "a" * 64, 0) == (text, conf) and ocr.cache_hits == 1


def test_reports_quoted_in_notes_are_cross_referenced_not_dropped():
    """2026-09-28: radiology reports can also appear inside clinical notes; keep the report, record where it's quoted."""
    from pipeline.dedup import find_duplicates, find_quotes
    from pipeline.extract import Document
    report = "CT CHEST ABDOMEN PELVIS\nExam Date: 04/10/2024\nIMPRESSION: Right adrenal nodule 1.2 x 1.0 cm. Stable osseous findings."
    note = ("Oncology follow-up\nDate of Service: 04/19/2024\nHistory reviewed in detail with the patient today.\n" + report +
            "\nPlan: continue capecitabine, repeat imaging in November, labs every two weeks, " * 3)
    docs = [Document("r1", "rad", "r.pdf", [report], "pdf"), Document("n1", "notes", "n.pdf", [note], "pdf")]
    kept, dropped = find_duplicates(docs)
    assert len(kept) == 2 and not dropped, "a report quoted in a larger note is not a duplicate"
    assert find_quotes(docs) == {"r1": ["n1"]}
    earlier = Document("n0", "notes", "m.pdf", [note.replace("04/19/2024", "03/01/2024")], "pdf")
    assert find_quotes([docs[0], earlier]) == {}, "a note dated before the report can't be quoting it"


def test_imaging_reports_linked_to_notes_that_cite_the_exam():
    from pipeline.core import link_imaging
    from pipeline.extract import Document
    mk = lambda i, t, typ, d: {"id": i, "doc": Document(i, "s", "f", [t], "pdf"), "pages": [t], "type": typ, "date": d}
    rep = mk("rad1", "Exam: PET/CT SKULL BASE TO MID THIGH\nIMPRESSION: solitary right adrenal nodule", "imaging", date(2024, 5, 2))
    note = mk("onc1", "--PET scan [5/2/2024] = solitary R adrenal nodule 1.1 x 1.3 cm", "oncology-follow-up", date(2024, 5, 17))
    other = mk("onc2", "--CT CAP [4/10/2024] = R adrenal nodule; labs 5/2/2024 normal", "oncology-follow-up", date(2024, 4, 19))
    results = [rep, note, other]
    link_imaging(results)
    assert rep["modality"] == "PET" and rep["referenced_in"] == ["onc1"], "same date but a different exam is not a citation"


def test_label_on_own_line_value_on_next():
    """Regression (2026-09-28): a portal demographics PDF leaked 'Patient Identifier\n<6 digits>' and a
    'Previous Name' value; a bare 'Name' column header must not hide the drug under it."""
    from pipeline import rules
    from pipeline.verify import WARN_PATTERNS
    t = ("Name\n[PATIENT]\nPrevious Name\nJane Q Doe\nPatient Identifier\n583014\nMedications\nName\n"
         "Carboxymethylcellulose 0.5% drops\nEmergency Contact:\nJohn Doe (spouse)\nWBC 5.2\n2026")
    got = {(s.source, t[s.start:s.end]) for s in rules.detect(t, rules.Denylist({})) if s.source.endswith("next-line")}
    assert got == {("id-next-line", "583014"), ("name-next-line", "Jane Q Doe"), ("name-next-line", "John Doe (spouse)")}
    rx = dict(WARN_PATTERNS)["bare-number-line"]
    assert [m.group("v") for m in rx.finditer("Patient Identifier\n583014\nWBC 5.2\n2026")] == ["583014"]


def test_two_line_checks_ignore_labels_ranges_and_time_rows():
    from pipeline import rules
    from pipeline.verify import WARN_PATTERNS
    t = "Patient Name:\nDate of Birth:\nPrevious Name\n          \nPatient Name:\nJane Q Doe"
    got = [t[s.start:s.end] for s in rules.detect(t, rules.Denylist({})) if s.source == "name-next-line"]
    assert got == ["Jane Q Doe"], got
    rx = dict(WARN_PATTERNS)["bare-number-line"]
    txt = "Glucose 98 mg/dL (H)\n70 - 110\n2215 2230 2245\n0250 1\n583014\n555-0144\n2026"
    assert [m.group("v") for m in rx.finditer(txt)] == ["583014", "555-0144"]


def test_dob_label_wins_over_identical_id_match():
    """Regression (2026-09-28): the DOB also listed under [patient] ids turned [DOB; age N] into [ID]."""
    from pipeline.core import merge
    from pipeline.rules import Span
    spans = merge([Span(5, 15, "ID", "denylist", "[ID]"), Span(5, 15, "DOB", "denylist", "[DOB]")])
    assert [(s.cat, s.token) for s in spans] == [("DOB", "[DOB]")]


def test_ids_entries_normalised():
    from pipeline import rules
    ids, dates = rules.normalized_ids({"patient": {"ids": ["MRN: 1234567", "DOB: 4/12/1961", "04/12/1961", "Acct #: A-99812734", "7654321"]}})
    assert ids == ["1234567", "A-99812734", "7654321"] and dates == ["4/12/1961", "04/12/1961"]
    den = rules.Denylist({"patient": {"ids": ["DOB: 4/12/1961"]}})
    t = "DOB: 4/12/1961"
    assert [(t[s.start:s.end], s.cat) for s in den.find(t)] == [("4/12/1961", "DOB")], "label text kept, labelled DOB"


def test_space_less_pdf_text_still_redacts_known_identifiers():
    """Regression (2026-09-28): radiology PDFs lost their spaces; 'Patient:NameDOB:<date>ExamDate:' leaked the DOB,
    and the same exact-match pattern made the leak check miss it."""
    from pipeline import rules
    ids = {"patient": {"dob": "1961-04-12", "ids": ["00473921"], "phones": ["555-555-0144"],
                       "addresses": ["2200 Sunrise Rd, Fairview, TX 78990"]}}
    den = rules.Denylist(ids)
    t = "Patient:ThornburyDOB:4/12/1961ExamDate:5/2/2024AccNo:00473921RN:Ph5555550144 2200SunriseRd"
    found = {t[s.start:s.end] for s in rules.detect(t, den)}
    for v in ["4/12/1961", "00473921", "2200SunriseRd"]:
        assert v in found, f"missed in glued text: {v}"
    assert not any(v in found for v in ["5/2/2024"]), "the exam date is not the DOB"
