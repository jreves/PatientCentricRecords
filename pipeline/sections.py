"""Split hospital encounter exports into their sections.

Epic "encounter" exports (e.g. a whole ED visit or admission, hundreds of pages) repeat a
header on every page:

    <Hospital> [PATIENT]
    <address> MRN: [ID], DOB: ..., Sex: F
    <address> Adm: 6/12/2023, D/C: 6/14/2023
    06/12/2023 - ED to Hosp-Admission (Discharged) in <unit> (continued)
    <Section title> (continued)

A section starts on the page where its title appears without "(continued)". Each section
becomes its own output document with a type, and a flag saying whether it is clinical
narrative (kept in the combined file for analysis) or administrative bulk (orders,
flowsheets, the medication administration record), which is only in the full combined file.
Runs on redacted text, so it can be tuned by reading published output.
"""
import re
from dataclasses import dataclass

from .chrono import parse_date

ENC_LINE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4}) - (.+?) (?:in|at) (.+?)(?: \(continued\))?$")
ADM_LINE = re.compile(r"Adm: (\d{1,2}/\d{1,2}/\d{4})(?:, D/C: (\d{1,2}/\d{1,2}/\d{4}))?")
CONTINUED = re.compile(r"\s*\(continued\)\s*$")

# (title regex, type, clinical?) checked in order; the first match wins.
SECTION_TYPES = [
    (r"ED Provider Note", "ed-provider-note", True),
    (r"ED Notes|ED Care Timeline", "ed-course", True),
    (r"H&P", "hospital-h&p", True),
    (r"Discharge Summary", "discharge-summary", True),
    (r"Op(?:erative)? (?:Note|Report)|Brief Op", "operative", True),
    (r"Clinical Notes|Progress Notes|Consult", "hospital-clinical-notes", True),
    (r"^Labs\b|Laborator", "labs", True),
    (r"Imaging|Radiology", "imaging", True),
    (r"^Procedures\b|Cardiac Results", "procedures", True),
    (r"^Medication List", "medication-list", True),
    (r"After Visit Summary|Discharge Instructions", "discharge-instructions", True),
    (r"Anesthesia", "anesthesia-record", False),
    (r"^(?:Case )?\[ID\]|\bCase\b", "surgical-case-record", False),
    (r"Medication Administration|MED ADMIN", "medication-administration", False),
    (r"Orders", "orders", False),
    (r"Flowsheets|SmartForms", "flowsheets", False),
    (r"Care Plan", "care-plan", False),
]
TYPE_RES = [(re.compile(rx), t, c) for rx, t, c in SECTION_TYPES]


@dataclass
class Section:
    title: str
    type: str
    clinical: bool
    parts: list          # [(0-based page index, text)] with the repeated page header removed

    @property
    def pages(self):
        return [i for i, _ in self.parts]


@dataclass
class Encounter:
    date: object         # admission / encounter date
    discharge: object
    kind: str            # e.g. "ED to Hosp-Admission (Discharged)"
    sections: list


def _header_end(lines):
    """Index just past the repeated page header, or None if this page has none."""
    end = None
    for i, line in enumerate(lines[:6]):
        if ENC_LINE.match(line) or ADM_LINE.search(line):
            end = i + 1
    return end


def section_type(title):
    for rx, t, clinical in TYPE_RES:
        if rx.search(title):
            return t, clinical
    return "encounter-admin", False   # face sheet, coding, events, approvals, documents...


def split_encounter(pages, textless=()):
    """-> Encounter if these pages are an encounter export, else None."""
    lines_by_page = [[l.strip() for l in p.splitlines() if l.strip()] for p in pages]
    headed = [i for i, ls in enumerate(lines_by_page) if any(ENC_LINE.match(l) for l in ls[:6])]
    text_pages = [i for i in range(len(pages)) if i + 1 not in textless]
    if len(pages) < 10 or len(headed) < 0.5 * max(1, len(text_pages)):
        return None
    enc = next(ENC_LINE.match(l) for l in lines_by_page[headed[0]][:6] if ENC_LINE.match(l))
    adm = next((m for ls in lines_by_page for m in [ADM_LINE.search(" ".join(ls[:6]))] if m), None)
    start = parse_date(adm.group(1)) if adm else parse_date(enc.group(1))
    discharge = parse_date(adm.group(2)) if adm and adm.group(2) else None

    # The running section title under the page header names the section the page is in. A
    # section usually starts part-way down the previous page (so its first header already
    # says "(continued)"); that page is split at the line where the bare title appears.
    key = lambda name: re.sub(r"^Case\s+", "", name)   # "Case [ID] (...)" == "[ID] (...)"
    sections, current = [], None
    for i, ls in enumerate(lines_by_page):
        end = _header_end(ls)
        title_line = ls[end] if end is not None and end < len(ls) else None
        name = CONTINUED.sub("", title_line)[:80] if title_line else None
        body = ls[end + 1:] if title_line and CONTINUED.search(title_line) else ls[end:] if end is not None else ls
        text = "\n".join(body)
        if current is not None and (name is None or key(name) == key(current.title)):
            current.parts.append((i, text))
            continue
        name = name or "Cover pages"
        t, clinical = section_type(name) if name != "Cover pages" else ("encounter-admin", False)
        new = Section(name, t, clinical, [])
        if current is not None and title_line and CONTINUED.search(title_line):
            prev_i, prev_text = current.parts[-1]
            prev_lines = prev_text.split("\n")
            cut = next((k for k, l in enumerate(prev_lines) if l.strip() == name), None)
            if cut is not None:
                current.parts[-1] = (prev_i, "\n".join(prev_lines[:cut]))
                new.parts.append((prev_i, "\n".join(prev_lines[cut:])))
        new.parts.append((i, text))
        sections.append(new)
        current = new
    return Encounter(start, discharge, enc.group(2), sections)
