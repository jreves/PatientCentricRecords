"""Note date and note type, derived from the already de-identified text.

Because this runs on redacted text, it can be tuned by inspecting the published
output, without anyone needing to look at raw notes.
"""
import re
from datetime import date

from .rules import DATE, DATE_RE

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# (label regex, weight). Higher weight = more likely to be the note's own date.
# Label words may run together in some PDFs ("DateofService", 2026-09-28), so spaces are optional.
DATE_LABELS = [
    (r"Date[ \t]*of[ \t]*Service|DOS|Service[ \t]*Date", 10),
    (r"Visit[ \t]*Date|Date[ \t]*of[ \t]*Visit|Encounter[ \t]*Date|Appointment[ \t]*Date|Appt[ \t]*Date", 9),
    (r"Date[ \t]*of[ \t]*(?:Surgery|Operation)|Operation[ \t]*Date|Surgery[ \t]*Date|Procedure[ \t]*Date"
     r"|Date[ \t]*of[ \t]*Procedure", 9),
    (r"Admission[ \t]*Date|Admit[ \t]*Date|Date[ \t]*of[ \t]*Admission"
     r"|Exam[ \t]*Date|Date[ \t]*of[ \t]*Exam|Study[ \t]*Date", 8),
    (r"Collection[ \t]*Date|Date[ \t]*Collected|Collected", 7),
    (r"Report[ \t]*Date|Note[ \t]*Date|Date[ \t]*of[ \t]*Note|Discharge[ \t]*Date|Date[ \t]*of[ \t]*Discharge", 6),
    (r"Received", 5),
    # a list kept up to date by the family ("Last updated October 10, 2026", often in a Word footer)
    (r"(?:Last[ \t]*)?(?:updated|revised|modified)(?:[ \t]*on)?", 5),
    (r"(?:Electronically[ \t]*)?Signed(?:[ \t]*(?:on|by))?", 4),
    (r"Date", 3),
]
LABEL_RES = [(re.compile(rf"\b(?:{lab})\b[^\n\d]{{0,25}}?({DATE})", re.I), w) for lab, w in DATE_LABELS]

NOTE_TYPES = [
    ("medication-list", r"current med(?:ication)?s\b|medication list"),
    ("pathology", r"surgical pathology|pathology report|cytology|final (?:pathologic )?diagnosis|immunohistochem"),
    ("genomics", r"foundation ?one|guardant|tempus|caris|next[- ]generation sequencing|genomic profil"),
    ("operative", r"operative report|op(?:erative)? note|procedure note"),
    ("discharge-summary", r"discharge summary"),
    ("admission-h&p", r"history and physical|\bh&p\b|admission note"),
    ("emergency", r"emergency department|\bed visit\b|emergency room"),
    ("imaging", r"mammogra|ultrasound|\bmri\b|\bct\b|pet/ct|pet-ct|bone scan|nuclear medicine|x-?ray|xr|radiograph"
                r"|echocardiogra|muga|dexa"),
    ("infusion", r"infusion|chemotherapy administration|treatment note"),
    ("lab", r"lab(?:oratory)? results?|\bcbc\b|comprehensive metabolic"),
    ("consult", r"consult"),
    ("telephone", r"telephone|phone call|patient message|mychart"),
    ("progress-note", r"progress note|follow[- ]up|office visit|clinic note|return visit|established patient"),
]
TYPE_RES = [(name, re.compile(rx, re.I)) for name, rx in NOTE_TYPES]


def parse_date(s, earliest=1980):
    s = s.strip()
    try:
        if m := re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s):
            mo, d, y = map(int, m.groups())
        elif m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
            y, mo, d = map(int, m.groups())
        elif m := re.fullmatch(r"([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", s):
            mo, d, y = MONTHS[m.group(1)[:3].lower()], int(m.group(2)), int(m.group(3))
        elif m := re.fullmatch(r"(\d{1,2})[- ]([A-Za-z]+)[- ,]+(\d{2,4})", s):
            d, mo, y = int(m.group(1)), MONTHS[m.group(2)[:3].lower()], int(m.group(3))
        else:
            return None
        if y < 100:
            y += 2000 if y <= 40 else 1900
        result = date(y, mo, d)
    except (ValueError, KeyError):
        return None
    return result if earliest <= result.year <= date.today().year + 1 else None


def age_at(dob, on):
    """Whole years from dob to the note date; Safe Harbor style "90+" at the top end."""
    if not dob or not on:
        return None
    age = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
    if not 0 <= age <= 120:
        return None
    return "90+" if age >= 90 else str(age)


def note_date(pages):
    """-> (date|None, basis) where basis says how the date was chosen."""
    text = "\n".join(pages)
    best = None
    for rx, weight in LABEL_RES:
        for m in rx.finditer(text):
            d = parse_date(m.group(1))
            if d and (best is None or weight > best[0] or (weight == best[0] and m.start() < best[1])):
                label = re.sub(r"\s+", " ", m.group(0)[:m.start(1) - m.start()]).strip(" :#-\t")
                best = (weight, m.start(), d, f"label '{label}'")
    if best:
        return best[2], best[3]
    for m in DATE_RE.finditer(pages[0] if pages else ""):
        if d := parse_date(m.group(0)):
            return d, "first date on page 1 (low confidence)"
    return None, "no date found"


ORG_HINT = re.compile(r"\b(?:Oncology|Hospital|Clinic|Center|Centre|Care|Health|Medical|Institute|Imaging|Radiology"
                      r"|Pathology|Laborator(?:y|ies)|Associates|Physicians|Surgery)\b")


def clinic(pages):
    """The practice/site named near the top, e.g. 'Lakeside Oncology Millbrook', 'St Example Hospital'.
    Tokens are dropped ("St Example Hospital [PATIENT]"), as is a "Source:" prefix."""
    first = next((p for p in pages if p.strip()), "")
    # The XML reader's explicit custodian line is trusted as is ("Source: Example Health Millbrook").
    if first.startswith(("C-CDA:", "Inpatient Summary", "Summarization")) or "\nC-CDA: " in first[:300]:
        src = re.search(r"^Source: (.+)$", first, re.M)
        if src and "[" not in src.group(1):
            return src.group(1).strip()
    for line in first.splitlines()[:8]:
        line = re.sub(r"^Source:\s*", "", re.sub(r"\s*\[[A-Z]+(?:-\d+)?[^\]]*\]\s*", " ", line)).strip()
        if line and len(line) <= 80 and ORG_HINT.search(line) and not re.search(r"\d{2}/\d{2}|DOB|MRN", line):
            return line
    return None


# Hospital export formats that state their own date and kind; checked before everything else.
PORTAL_NOTE_KINDS = [
    (r"ED Provider Notes?", "ed-provider-note"), (r"H&P", "hospital-h&p"), (r"Op(?:erative)? (?:Note|Report)", "operative"),
    (r"Discharge Summary", "discharge-summary"), (r"Progress Notes?", "hospital-progress-note"),
    (r"Consult(?:ation)?(?: Notes?)?", "consult"), (r"Procedure Notes?", "procedure-note"),
]


CCDA_KINDS = [
    (r"Inpatient Summary", "inpatient-summary"), (r"Discharge Summary", "discharge-summary"),
    # Patient-portal visit exports ("View, Download, and Transmit Summary Document"): clinic visits.
    (r"View, Download,? and Transmit|Visit Summary|Clinical Summary|Ambulatory Summary", "outpatient-visit"),
    (r"History (?:and|&) Physical", "hospital-h&p"), (r"Operative|Procedure Note", "operative"),
    (r"Consultation", "consult"), (r"Progress Note", "hospital-progress-note"),
    (r"Diagnostic Imaging|Imaging Report", "imaging"), (r"Emergency", "ed-provider-note"),
]


def hospital_format(pages):
    """-> (date, basis, type) for recognised hospital exports, else None."""
    text = "\n".join(pages)
    head = text[:1500]
    # Normalised header emitted by the C-CDA XML reader (ccda.py).
    if m := re.search(r"^C-CDA: (.+?) \| (\d{1,2}/\d{1,2}/\d{4}|\?) to (\d{1,2}/\d{1,2}/\d{4}|\?)", head, re.M):
        kind, low, high = m.groups()
        title = head.split("\n", 1)[0]
        mapped = next((t for rx, t in CCDA_KINDS if re.search(rx, f"{title} {kind}", re.I)), "encounter-summary")
        if low != "?":
            return parse_date(low), f"episode {low} to {high}", mapped
    if m := re.search(r"Summarization of Episode Note \| (\d{1,2}/\d{1,2}/\d{4}) to (\d{1,2}/\d{1,2}/\d{4})", head):
        kind = "inpatient-summary" if "Inpatient Summary" in head else "encounter-summary"
        return parse_date(m.group(1)), f"episode {m.group(1)} to {m.group(2)}", kind
    if "Full Encounter Summary" in head and (m := re.search(r"Appt\.\s*(?:\n\s*)?Name\s+(\d{1,2}/\d{1,2}/\d{4})", head)):
        return parse_date(m.group(1)), f"appointment {m.group(1)}", "outpatient-visit"
    # Patient-portal copies of hospital notes: "<Kind> by <author> at <date>" near the top.
    for rx, kind in PORTAL_NOTE_KINDS:
        if m := re.search(rf"^{rx}\b[^\n]*(?:\n[^\n]*)?? at (\d{{1,2}}/\d{{1,2}}/\d{{4}})", head, re.M):
            return parse_date(m.group(1)), f"{kind} dated {m.group(1)}", kind
    if m := re.search(r"Note From Your (?:Admission|Visit|Encounter) on (\d{1,2}/\d{1,2}/\d{2,4})", head):
        return parse_date(m.group(1)), f"portal note, encounter {m.group(1)}", "hospital-note"
    return None


# Visit notes from the oncology EHR template (every current note) share one layout and carry
# no title, so the kind of visit is read from specific phrases; checked in order.
VISIT_TYPES = [
    # Later visits carry the consult's HPI forward ("presents for initial consultation"), so a
    # note that also says it is a follow-up is one.
    ("palliative-care-consult", lambda t, c: _palliative(t, c) and re.search(r"initial consult", t, re.I)
     and not FOLLOW_UP.search(t)),
    ("palliative-care-follow-up", lambda t, c: _palliative(t, c)),
    ("radiation-oncology-follow-up", lambda t, c: re.search(
        r"CHIEF COMPLAINT:[^\n]*(?:\n[^\n]*){0,2}(?:radiotherapy|radiation)", t, re.I)),
    ("treatment-review", lambda t, c: re.search(r"treatment review and coordination of care", t, re.I)),
    ("oncology-consult", lambda t, c: re.search(r"History of Present Illness", t) and re.search(
        r"initial consult|new patient consult|establish(?:es|ing)? care", t, re.I) and not FOLLOW_UP.search(t)),
    ("oncology-follow-up", lambda t, c: re.search(r"History of Present Illness|INTERVAL HISTORY", t, re.I)
     and re.search(r"follow[- ]?up|Interval History", t, re.I)),
]


FOLLOW_UP = re.compile(r"(?:present(?:s|ing)|returns?|here|seen) (?:today )?for (?:a )?(?:scheduled )?follow[- ]?up", re.I)


def _palliative(text, site):
    return bool((site and "Palliative" in site) or "SYMPTOM MANAGEMENT:" in text)


def table_dates(pages):
    """A spreadsheet is a series, not one note: date it by its earliest row, record the span."""
    dates = sorted(d for m in DATE_RE.finditer("\n".join(pages)) if (d := parse_date(m.group(0))))
    if not dates:
        return None, "no date found"
    return dates[0], f"spreadsheet rows dated {dates[0]} to {dates[-1]} ({len(dates)} dates)"


def note_type(pages, kind=None):
    text = "\n".join(pages)
    site = clinic(pages)
    for name, test in VISIT_TYPES:
        if test(text, site):
            return name
    # Other document kinds (future sources): keywords near the top of the first page.
    head = (pages[0] if pages else "")[:600]
    hits = [(m.start(), name) for name, rx in TYPE_RES if (m := rx.search(head))]
    if hits:
        return min(hits)[1]
    return "spreadsheet" if kind == "xlsx" else "note"
