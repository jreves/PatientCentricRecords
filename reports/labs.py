"""Blood counts from the published notes' lab tables ("LabResults <dates>" then one row per test).
A row is used only when it has exactly one value per date (chemistry rows sometimes skip cells, which would misalign them).
Where two notes report the same test and date, the later note wins.

The table format and row labels (``labs:`` in the case file) follow the oncology EHR the notes came from; adjust them there
for another practice's format."""
import re

from . import common

DEFAULT_TESTS = {"WBC": r"WBC\b", "ANC": r"Neu # \(ANC\)", "HGB": r"HGB\b", "PLT": r"PLT\b"}
DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
VAL = re.compile(r"(\d+(?:\.\d+)?)(?:\s*\((?:L|H)\))?")


def notes():
    return common.case().notes


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
        if header not in text:
            continue
        lines = text.splitlines()
        hit = False
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
