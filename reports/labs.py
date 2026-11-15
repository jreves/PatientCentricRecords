"""Lab values from the published notes, in two layouts:
- lab tables in visit notes ("LabResults <dates>" then one row per test). A row is used only when it has exactly one value
  per date (chemistry rows sometimes skip cells, which would misalign them);
- result rows of C-CDA documents as the pipeline renders them ("<panel> | <test unit (range)> | <value> | <YYYY-MM-DD>"),
  one value and its date per row.
Where two notes report the same test and date, the later note wins.

The table format and row labels (``labs:`` in the case file) follow the oncology EHR the notes came from; adjust them there
for another practice's format."""
import re

from . import common

DEFAULT_TESTS = {"WBC": r"WBC\b", "ANC": r"(?:Neu # \(ANC\)|\bANC \(M\))", "HGB": r"HGB\b", "PLT": r"PLT\b"}
DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
VAL = re.compile(r"(\d+(?:\.\d+)?)(?:\s*\((?:L|H)\))?")
# a C-CDA result row: panel | component (with its unit and range) | value | date
CCDA_ROW = re.compile(r"^[^|\n]*\| (?P<comp>[^|\n]+?) \| [<>]?(?P<val>\d+(?:\.\d+)?)\s*(?:\(?[LH]\)?)? \| (?P<date>\d{4}-\d{2}-\d{2})\b", re.M)


def ccda_unit(unit):
    """A table unit pattern as C-CDA rows write it: no "x " before 10^3, and microlitres as uL, µL or a garbled "?l"."""
    return unit.replace("x ", "(?:x )?").replace("uL", r"(?:uL|µL|μL|\?+l)")


def notes():
    return common.case().notes


# a visit-note table cell: one value, or several for the same date joined by ";" (e.g. two methods run side by side)
CELL = re.compile(r"\d+(?:\.\d+)?(?:\s*\([LH]\))?(?:;\s*\d+(?:\.\d+)?(?:\s*\([LH]\))?)*")


def results(pattern, unit):
    """Every reported value of one test, keeping same-day repeats: {iso date: [(value, panel, doc id)]}.

    Unlike ``parse`` (one value per date, for charts), this is for checking a series against the records: a lab that
    runs an old and a new method on the same blood reports two values that day, under two panel names in a visit
    summary ("<panel> | <test> | value | date") and as "a; b" in a visit-note table (panel shown as "visit-note table")."""
    found = {}
    for f in sorted(notes().glob("*.md")):
        doc = f.stem.rsplit("_", 1)[-1]
        text = f.read_text(encoding="utf-8")
        for m in CCDA_ROW.finditer(text):
            if re.match(pattern + r"[^\d|]*?" + ccda_unit(unit), m.group("comp")):
                found.setdefault(m.group("date"), []).append((float(m.group("val")), m.group(0).split("|")[0].strip(), doc))
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not line.startswith("LabResults"):
                continue
            dates = [f"{y}-{mo}-{d}" for mo, d, y in DATE.findall(line)]
            for row in lines[i + 1:i + 30]:
                if row.startswith("LabResults"):
                    break
                m = re.match(pattern + r"[^\d]*?" + unit + r"\s+(.*)$", row)
                cells = CELL.findall(m.group(1)) if m else []
                if m and len(cells) == len(dates):
                    for d, cell in zip(dates, cells):
                        for v in re.findall(r"\d+(?:\.\d+)?(?!\d)(?=\s*(?:\([LH]\))?\s*(?:;|$))", cell):
                            found.setdefault(d, []).append((float(v), "visit-note table", doc))
    out = {}
    for d, rows in found.items():   # one entry per value and day: prefer a named panel, list each note once
        by_val = {}
        for v, panel, doc in rows:
            p, docs = by_val.get(v, ("", []))
            by_val[v] = (p if p and p != "visit-note table" else panel or p, docs + [doc] if doc not in docs else docs)
        out[d] = [(v, p or "result", sorted(docs)) for v, (p, docs) in sorted(by_val.items())]
    return out


def parse(tests=None):
    """{test: {iso_date: value}} plus the number of notes that contributed.

    tests: {key: pattern} (rows whose unit matches ``labs.units_pattern``) or {key: [pattern, unit pattern]}; default the
    case's ``labs.tests``, else the four blood counts."""
    cfg = common.case().get("labs", {})
    tests = tests or cfg.get("tests", DEFAULT_TESTS)
    header = cfg.get("header", "LabResults")
    units = cfg.get("units_pattern", r"(?:x 10\^\d/uL|g/dL)")
    tests = {k: (v, units) if isinstance(v, str) else tuple(v) for k, v in tests.items()}
    out = {k: {} for k in tests}
    used = 0
    for f in sorted(notes().glob("*.md")):
        text = f.read_text(encoding="utf-8")
        hit = False
        for m in CCDA_ROW.finditer(text):   # the component: the test's row label, then its unit (written without "x ")
            for key, (pat, unit) in tests.items():
                if re.match(pat + r"[^\d|]*?" + ccda_unit(unit), m.group("comp")):
                    out[key][m.group("date")] = float(m.group("val"))
                    hit = True
        if header not in text:
            used += hit
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not line.startswith(header):
                continue
            dates = [f"{y}-{m}-{d}" for m, d, y in DATE.findall(line)]
            if not dates:
                continue
            for row in lines[i + 1:i + 30]:
                if row.startswith(header):
                    break
                for key, (pat, unit) in tests.items():
                    m = re.match(pat + r"[^\d]*?" + unit + r"\s+(.*)$", row)
                    if not m:
                        continue
                    vals = [float(v) for v in VAL.findall(m.group(1))]
                    if len(vals) == len(dates):
                        for d, v in zip(dates, vals):
                            out[key][d] = v
                        hit = True
        used += hit
    return out, used
