"""Source audit: is every detailed assertion in the reports grounded in a specific de-identified note?

The reports are drawn entirely from the case file, so the audit checks the case file: every claim it contains (a
treatment, an event, a scan, a table row, an emergency-card line, a sentence block of the narrative) must cite its
sources in ``citations.yaml`` beside the case:

    event/2025-02-11/hosp:
      src:
        - {doc: ex00000002, quote: "Admitted 2/11/2025 with dehydration"}   # a published note and a verbatim quote from it
        - {family: "confirmed by the family, 3/2025"}                     # or a family report, listed as such
      accept: {"1.4 cm": "the size is in the report's table, which the extractor split"}   # optional, with a reason
      reviewed: "what was checked by hand where the local model doubted the claim"     # optional

Checks, all local:
1. **Citation:** the note exists in the published notes and the quote appears in it, word for word.
2. **Details:** every date, dose/measurement, drug or test name and clinician surname in the claim appears in at least
   one cited note (dates in any common format; approximate dates to the month).
3. **Meaning** (``--no-semantic`` to skip): the local model reads the claim and the cited passages and says whether they
   support it. It is a second, independent reader, not the authority.

Statuses: grounded · partial (a detail not found in the cited notes) · broken (citation does not check out) ·
unsourced · family-reported. The audit warns; it never blocks a build. Its appendix lists every claim with its
sources for a clinician to check, worklist first. Console output is counts only.

``--suggest`` proposes sources for unsourced claims (the notes containing the most of a claim's details, and the line
that holds them) in ``citations.suggested.yaml``, for review before they are copied into ``citations.yaml``.
"""
import hashlib
import html
import json
import re
import urllib.error
import urllib.request
from datetime import date
from html.parser import HTMLParser

import yaml

from . import common
from .common import e, fmt

C = common.case()
A = C.get("audit", {})
SOURCES = C.dir / "citations.yaml"
AUTHORITATIVE = {a["doc"]: a for a in A.get("authoritative", [])}   # notes that outrank the rest for what they cover
SUGGESTED = C.dir / "citations.suggested.yaml"
TERMS_FILE = common.case_mod.ROOT / "config" / "medical_terms.txt"

# Brand and generic names that refer to the same drug (extend in the case: audit.synonyms).
SYNONYMS = {
    "abraxane": ["nab-paclitaxel", "paclitaxel protein-bound", "protein-bound paclitaxel"],
    "datopotamab deruxtecan": ["datroway", "dato-dxd", "datopotamab"], "datroway": ["datopotamab"],
    "zoledronic acid": ["zometa", "zoledronic", "reclast"], "zometa": ["zoledronic"],
    "doxorubicin": ["adriamycin"], "cyclophosphamide": ["cytoxan"],
    "capecitabine": ["xeloda"], "palbociclib": ["ibrance"], "alpelisib": ["piqray"], "fulvestrant": ["faslodex"],
    "letrozole": ["femara"], "anastrozole": ["arimidex"], "exemestane": ["aromasin"], "gemcitabine": ["gemzar", "avgemsi"],
    "pred forte": ["prednisolone"], "prednisolone": ["pred forte"], "denosumab": ["xgeva", "prolia"],
    "trastuzumab deruxtecan": ["enhertu"], "sacituzumab govitecan": ["trodelvy"],
}
for k, v in A.get("synonyms", {}).items():
    SYNONYMS.setdefault(k.lower(), []).extend(x.lower() for x in v)

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
UNITS = r"mg/m²|mg/m2|mg/kg|mg/dl|mg/ml|mcg|mg|g/dl|cgy|gy|cm|mm|u/ml|lb|ml|%"
QTY = re.compile(rf"(?<![\d.])(\d+(?:\.\d+)?)\s*({UNITS})(?![a-z])", re.I)
DR = re.compile(r"\bDr\.?\s+(?:[A-Z][a-z]+\s+)?(?:[A-Z]\.?\s+)?([A-Z][a-zA-Z\-]{2,})")


# --- normalisation ---------------------------------------------------------------------------------------------------
def strip_html(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", str(s or "")))


def norm(s, markup=True):
    """Lower-cased, dashes and units unified, whitespace collapsed. Claims may carry HTML (markup=True); note text
    never does, and stripping "tags" from it would delete everything between a "<" and a ">" (lab ranges like "<=0.5")."""
    s = (strip_html(s) if markup else html.unescape(str(s or "")))
    s = s.lower().replace("–", "-").replace("—", "-").replace("’", "'").replace("×", "x").replace("²", "2")
    s = re.sub(r"(\d)\s+(%|mg|cgy|gy|cm|mm|u/ml|lb|mcg|ml)(?![a-z])", r"\1\2", s)   # "1 %" -> "1%" (no \b after "%")
    return re.sub(r"\s+", " ", s).strip()


def year(y):
    y = int(y)
    return y + 2000 if y < 50 else y + 1900 if y < 100 else y


def doc_dates(text):
    """({(y, m, d)}, {(y, m)}) for every date written in a note."""
    days, months = set(), set()
    for a, b, c in re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", text):
        if 1 <= int(a) <= 12 and 1 <= int(b) <= 31:
            days.add((year(c), int(a), int(b)))
    for a, b, c in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        days.add((int(a), int(b), int(c)))
    for mo, d, y in re.findall(r"\b([A-Z][a-z]{2})[a-z]*\.? (\d{1,2}),? (\d{4})\b", text):
        if mo.lower() in MONTHS:
            days.add((int(y), MONTHS[mo.lower()], int(d)))
    for mo, y in re.findall(r"(?<![\d/])(\d{1,2})/(\d{4})\b", text):
        if 1 <= int(mo) <= 12:
            months.add((int(y), int(mo)))
    for mo, y in re.findall(r"\b([A-Z][a-z]{2})[a-z]* (\d{4})\b", text):
        if mo.lower() in MONTHS:
            months.add((int(y), MONTHS[mo.lower()]))
    return days, months | {(y, m) for y, m, _ in days}


def claim_dates(text):
    """[(y, m, d or None)] written in a claim's text: full dates, ranges like 6/25–6/28/2025, and month/year."""
    t = strip_html(text)
    out = []
    for a, b, c, d, y in re.findall(r"\b(\d{1,2})/(\d{1,2})\s*[–-]\s*(\d{1,2})/(\d{1,2})/(\d{4})\b", t):
        out += [(int(y), int(a), int(b)), (int(y), int(c), int(d))]
    t2 = re.sub(r"\b\d{1,2}/\d{1,2}\s*[–-]\s*\d{1,2}/\d{1,2}/\d{4}\b", " ", t)
    for a, b, c in re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", t2):
        if 1 <= int(a) <= 12:
            out.append((year(c), int(a), int(b)))
    for a, b, c in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", t2):
        out.append((int(a), int(b), int(c)))
    for mo, y in re.findall(r"(?<![\d/])(\d{1,2})/(\d{4})\b", t2):
        if 1 <= int(mo) <= 12:
            out.append((int(y), int(mo), None))
    return out


def load_terms():
    terms = set()
    if TERMS_FILE.exists():
        for line in TERMS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip().lower()
            if len(line) >= 6:
                terms.add(line)
    return terms | {k for k in SYNONYMS if len(k) >= 6}


TERMS = load_terms()


# --- claims ----------------------------------------------------------------------------------------------------------
def claim(key, area, label, text, dates=()):
    return {"key": key, "area": area, "label": strip_html(label).strip(), "text": strip_html(text).strip(),
            "dates": [(d, approx) for d, approx in dates if d]}


def iso_dates(*pairs):
    return [(d, a) for d, a in pairs if d and d != C.today]


def therapy_claims():
    out = []
    for g, bars in C.get("therapy_groups", {}).items():
        for b in bars:
            end = None if (b.get("ongoing") or b.get("continues")) else b["end"]
            ds = iso_dates((b["start"], b.get("startApprox", False)), (end, b.get("endApprox", False)))
            holds = " ".join(h[2] for h in b.get("holds", []))
            out.append(claim(f"therapy/{g}/{b['label']}/{b['start']}", "Treatments", b["label"], f"{b['label']}. {b.get('note', '')} {holds}", ds))
    return out


def event_claims():
    out = []
    for ev in C.get("early_events", []) + C.get("events", []):
        ds = [(ev["date"], False)] + [(d, False) for d in ev.get("stay", [])]
        out.append(claim(f"event/{ev['date']}/{ev['kind']}", "Events and procedures", f"{fmt(ev['date'])} {ev['kind']}", ev["text"], ds))
    for i in C.get("implants", []):
        out.append(claim(f"implant/{i['date']}/{i['component']}", "Implants", f"{fmt(i['date'])} {i['component']}",
                         f"{i['component']}: {i['spec']} ({i.get('manufacturer', '')}, catalog {i.get('catalog') or 'not recorded'}). "
                         f"{i.get('status', '')}", [(i["date"], False)]))
    for d, _, text in C.get("imaging", []):
        out.append(claim(f"imaging/{d}", "Imaging", f"{fmt(d)} imaging", text, [(d, False)]))
    for d, approx, text in C.get("adverse_events", []):
        out.append(claim(f"ae/{d}", "Side effects", f"{fmt(d)} side effect", text, [(d, approx)]))
    return out


def table_claims():
    out, T = [], C.get("treatments_table", {})
    for title, sub, rows in T.get("phases", []):
        if sub:
            out.append(claim(f"treatments/phase/{title}", "Treatments table", title, sub))
        line = ""
        for r in rows:
            line = r[0] or line
            out.append(claim(f"treatments/{line}/{r[1]}", "Treatments table", f"{line} {r[1]}", " · ".join(str(x) for x in r[1:] if x)))
    for r in T.get("radiation", []):
        out.append(claim(f"treatments/radiation/{r[0]}", "Treatments table", f"Radiation: {r[0]}", " · ".join(str(x) for x in r if x)))
    return out


def pathology_claims():
    out, P = [], C.get("pathology", {})
    for t in P.get("tests", []):
        res = "; ".join(f"{k} {v[1]}" for k, v in t.get("res", {}).items())
        out.append(claim(f"pathology/{t['id']}", "Pathology and genetics", f"{t['id']} {t['title']}",
                         f"{t['title']} ({t.get('lab', '')}): {t['summary']} {res}", [(t["date"], False)]))
    for d, what, note in P.get("untested", []):
        out.append(claim(f"pathology/untested/{d}", "Pathology and genetics", what, f"{what}: {note}", [(d, False)]))
    return out


def counts_claims():
    out = []
    for drug, _, segs, holds in C.get("blood_counts", {}).get("doses", []):
        for s0, s1, label in segs:
            out.append(claim(f"doses/{drug}/{s0}", "Doses", f"{drug} {label}", f"{drug}: {label}", iso_dates((s0, False))))
    for d, text in C.get("blood_counts", {}).get("events", []):
        out.append(claim(f"counts_event/{d}", "Doses", fmt(d), text, [(d, False)]))
    M = C.get("medications", {})
    for name, group, s0, s1, ongoing, note in M.get("extra", []):
        out.append(claim(f"medications/{name}", "Medications", name, f"{name}: {note}", iso_dates((s0, False), (None if ongoing else s1, False))))
    if M.get("current"):
        out.append(claim("medications/current", "Medications", "Current medication list", ", ".join(M["current"])))
    return out


def overview_claims():
    out, O = [], C.get("overview", {})
    for s in O.get("sites", []):
        out.append(claim(f"overview/site/{s['n']}", "Disease sites", s["site"], f"{s['site']}: first {s['first']} ({s['how']}). {s['course']}"))
    for ln in O.get("lines", []):
        best = f" Best response {fmt(ln[6][0])}: {ln[6][1]}." if ln[6] else ""
        out.append(claim(f"overview/line/{ln[0]}", "Treatment lines", f"{ln[0]} {ln[1]}", f"{ln[1]}.{best} {ln[7]}",
                         iso_dates((ln[6][0] if ln[6] else None, False))))
    if O.get("negative"):
        out.append(claim("overview/negative", "Disease sites", "Looked for and not found", O["negative"]))
    return out


def question_claims():
    out, Q = [], C.get("questions", {})
    for kind in ("disagree", "gaps"):
        for topic, shows, _ in Q.get(kind, []):
            out.append(claim(f"questions/{kind}/{topic}", "Open questions", topic, shows))
    for topic, text in Q.get("settled", []):
        out.append(claim(f"questions/settled/{topic}", "Open questions", topic, text))
    return out


def emergency_claims():
    out, E = [], C.get("emergency", {})
    for lab, v in E.get("fill_pdf", []):
        if v:
            out.append(claim(f"emergency/fill/{lab}", "Emergency summary", lab, v))
    if E.get("diagnosis_html"):
        out.append(claim("emergency/diagnosis", "Emergency summary", "Diagnosis line", E["diagnosis_html"]))
    for t, x in E.get("risks", []):
        out.append(claim(f"emergency/risk/{t}", "Emergency summary", t, x))
    for row in E.get("extra_labs", []):
        out.append(claim(f"emergency/lab/{row[0]}", "Emergency summary", row[0], " ".join(row)))
    if E.get("past"):
        out.append(claim("emergency/past", "Emergency summary", "Past cancer treatment", E["past"]))
    for m, dose, f, who in E.get("meds", []):
        out.append(claim(f"emergency/med/{m}", "Emergency summary", m, f"{m}, {dose}, for {f} ({who})"))
    for role, who, where in E.get("team", []):
        out.append(claim(f"emergency/team/{role}", "Emergency summary", role, f"{role}: {who}, {where}"))
    for v, d in E.get("vaccines", []):
        out.append(claim(f"emergency/vaccine/{v}", "Emergency summary", v, f"{v} {d}"))
    if E.get("hospitals"):
        out.append(claim("emergency/hospitals", "Emergency summary", "Hospitals", E["hospitals"]))
    return out


def chart_claims():
    out = []
    for cid, s in C.get("charts", {}).items():
        area = f"Chart: {cid}"
        for b in s.get("extra_bars", []) + s.get("bars", []):
            end = None if b.get("ongoing") or b.get("continues") else b["end"]
            out.append(claim(f"chart/{cid}/bar/{b.get('label', '')}/{b['start']}", area, b.get("label", ""), f"{b.get('label', '')}. {b.get('note', '')}",
                             iso_dates((b["start"], b.get("startApprox", False)), (end, b.get("endApprox", False)))))
        for m in s.get("extra_markers", []):
            out.append(claim(f"chart/{cid}/marker/{m['date']}", area, m["title"], m["text"], [(m["date"], False)]))
        for d, clinic, finding, proc in s.get("visits", []):
            out.append(claim(f"chart/{cid}/visit/{d}", area, f"{fmt(d)} {clinic}", f"{clinic}. {finding} {proc}", [(d, False)]))
        for d, text in s.get("notes", []):
            out.append(claim(f"chart/{cid}/note/{d}", area, fmt(d), text, [(d, False)]))
    return out


class Blocks(HTMLParser):
    """Text blocks of the narrative: list items, paragraphs, table rows and boxes, under their section heading."""
    TAGS = {"li", "p", "tr", "div"}

    def __init__(self):
        super().__init__()
        self.stack, self.blocks, self.section, self.head = [], [], "Introduction", None

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class", "") or ""
        if tag == "h2":
            self.head = []
        if tag == "td":   # a table row is a claim only if it has data cells (not a header row)
            for item in self.stack:
                if item[0] == "tr":
                    item.append("td")
        if tag in self.TAGS and not (tag == "div" and "box" not in cls.split()):
            self.stack.append([tag, []])

    def handle_endtag(self, tag):
        if tag == "h2" and self.head is not None:
            self.section, self.head = " ".join(self.head).strip(), None
        if self.stack and self.stack[-1][0] == tag:
            t, parts, *flags = self.stack.pop()
            text = re.sub(r"\s+", " ", " ".join(parts)).strip()
            if len(text) > 25 and "{{" not in text and not (t == "tr" and (not flags or not re.search(r"\d", text))):
                self.blocks.append((self.section, text))

    def handle_data(self, data):
        if self.head is not None:
            self.head.append(data)
        for item in self.stack[-1:]:
            item[1].append(data)


def narrative_claims():
    doc = C.get("document")
    if not doc:
        return []
    p = Blocks()
    p.feed((C.dir / doc["file"]).read_text(encoding="utf-8"))
    out, seen = [], {}
    for section, text in p.blocks:
        slug = re.sub(r"[^a-z0-9]+", "-", norm(text))[:48].strip("-")
        n = seen[slug] = seen.get(slug, 0) + 1
        out.append(claim(f"narrative/{slug}" + (f"/{n}" if n > 1 else ""), f"Narrative: {section}", text[:70], text))
    return out


def all_claims():
    return (therapy_claims() + event_claims() + table_claims() + pathology_claims() + counts_claims() + overview_claims()
            + question_claims() + emergency_claims() + chart_claims() + narrative_claims())


# --- atoms: the details a source must contain ----------------------------------------------------------------------
def atoms(c):
    """[(kind, display, test)] where test(doc) -> bool."""
    out, seen = [], set()

    def add(kind, disp, test):
        if (kind, disp.lower()) not in seen:
            seen.add((kind, disp.lower()))
            out.append((kind, disp, test))

    for iso, approx in c["dates"]:
        y, m, d = (int(x) for x in iso.split("-"))
        add("date", f"{m}/{y}", lambda doc, y=y, m=m: (y, m) in doc["months"])
    for y, m, d in claim_dates(c["text"]):
        if d:
            add("date", f"{m}/{d}/{y}", lambda doc, y=y, m=m, d=d: (y, m, d) in doc["days"])
        else:
            add("date", f"{m}/{y}", lambda doc, y=y, m=m: (y, m) in doc["months"])
    t = norm(c["text"])
    for num, unit in QTY.findall(strip_html(c["text"])):
        qs = [norm(f"{num}{unit}")]
        if unit.lower() == "gy":   # radiation doses are often written in cGy (20 Gy = 2000 cGy)
            qs.append(f"{float(num) * 100:g}cgy")
        add("amount", f"{num} {unit}", lambda doc, qs=qs: any(q in doc["norm"] for q in qs))
    for term in TERMS:
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", t):
            alts = [term] + SYNONYMS.get(term, [])
            add("term", term, lambda doc, alts=alts: any(a in doc["norm"] for a in alts))
    for surname in DR.findall(strip_html(c["text"])):
        s = surname.lower()
        add("clinician", f"Dr. {surname}", lambda doc, s=s: s in doc["norm"])
    return out


# --- notes -----------------------------------------------------------------------------------------------------------
def load_notes():
    notes = {}
    mpath = C.notes.parent / "manifest.json"
    meta = {m["doc_id"]: m for m in json.loads(mpath.read_text(encoding="utf-8"))} if mpath.exists() else {}
    for f in sorted(C.notes.glob("*.md")):
        did = f.stem.rsplit("_", 1)[-1]
        text = f.read_text(encoding="utf-8")
        m = meta.get(did, {})
        days, months = doc_dates(text)
        hd = re.search(r"^date: (\d{4})-(\d{2})-(\d{2})", text, re.M)
        if hd:
            y, mo, d = (int(x) for x in hd.groups())
            days.add((y, mo, d)); months.add((y, mo))
        notes[did] = {"id": did, "text": text, "norm": norm(text, markup=False), "days": days, "months": months,
                      "date": m.get("date") or (hd and "-".join(hd.groups())) or "", "type": m.get("type", ""), "clinic": m.get("clinic", "")}
    return notes


# --- semantic check (local model) ------------------------------------------------------------------------------------
SEM_PROMPT = """You check one statement from a family-prepared medical summary against excerpts from the patient's
de-identified medical records. Names of the patient and family are replaced by tokens such as [PATIENT].

STATEMENT:
{claim}

EXCERPTS FROM THE CITED RECORDS (each starts with the note's id, date, type, clinic and source):
{evidence}

Split the statement into its separate facts (each date, drug, dose, finding, procedure, place, person or outcome) and
decide for each whether the excerpts support it. Rules:
- Equivalent wording and notation count as support: mg/m2 = mg/m²; 2000 cGy = 20 Gy; OD = right eye, OS = left eye,
  OU = both eyes; nab-paclitaxel = Abraxane; a date written 3/23/24, 03/23/2024 or 2024-03-23 is the same date.
- A fact stated in the FAMILY REPORTS, or marked in the statement as a family report, is supported.
- Reading a term with medical knowledge is fine (AC = doxorubicin + cyclophosphamide); adding facts that are not in
  the excerpts is not.
- A fact is unsupported only if the excerpts do not state it or contradict it.
- List only facts that are in the statement; never add facts from the excerpts.
- A note marked AUTHORITATIVE is the best record of what it covers (e.g. the current medicines, with their doses and
  prescribers): it supports those facts, and where another record disagrees, it wins.
For each fact give the words in the excerpts that support it (empty if none)."""
SEM_SCHEMA = {"type": "object", "required": ["facts"], "properties": {"facts": {"type": "array", "items": {
    "type": "object", "required": ["fact", "supported", "evidence"], "properties": {
        "fact": {"type": "string"}, "supported": {"type": "boolean"}, "evidence": {"type": "string"}}}}}}


def verdict(answer):
    """supported / partial / unsupported from the model's fact-by-fact answer."""
    facts = answer.get("facts") or []
    ok = [f for f in facts if f.get("supported")]
    v = "supported" if facts and len(ok) == len(facts) else "unsupported" if not ok else "partial"
    return {"verdict": v, "facts": len(facts), "supported": len(ok),
            "unsupported_facts": [f["fact"] for f in facts if not f.get("supported")]}


NOTE_BUDGET, TOTAL_BUDGET = 4500, 13000   # characters of record text shown to the model per note, and in all


def evidence(c, docs, srcs, atom_list, family=()):
    """What the model reads: a short note whole; a long one as passages around the quote, each detail, each number and
    each content word of the claim. Then the family's reports, which count as support for what they state."""
    budget = max(1500, min(NOTE_BUDGET, TOTAL_BUDGET // max(1, len(srcs))))
    words = sorted(content_words(c["text"]), key=len, reverse=True)[:25]
    numbers = set(re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?![\d])", strip_html(c["text"])))
    parts = []
    for s in srcs:
        doc = docs[s["doc"]]
        text = doc["text"]
        body = text.split("\n---\n", 1)[-1] if text.startswith("---") else text
        if len(body) <= budget:
            excerpt = re.sub(r"\s+", " ", body)
        else:
            low, windows = body.lower(), []
            i = norm_find(body, s.get("quote", ""))
            if i is not None:
                windows.append((max(0, i - 600), i + len(s.get("quote", "")) + 600))
            keys = [disp.lstrip("~").replace("Dr. ", "").lower() for _, disp, _ in atom_list]
            keys += [n for n in numbers if len(n) >= 2] + words
            for k in keys:
                for m in list(re.finditer(re.escape(k), low))[:2]:
                    windows.append((max(0, m.start() - 220), m.end() + 220))
            merged = []
            for a, b in sorted(windows):
                if merged and a <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], b)
                else:
                    merged.append([a, b])
            excerpt = " … ".join(re.sub(r"\s+", " ", body[a:b]) for a, b in merged)[:budget]
        src = re.search(r"^source: (.*)$", text, re.M)
        auth = AUTHORITATIVE.get(doc["id"])
        tag = f", AUTHORITATIVE for {auth['covers']} as of {fmt(str(auth['as_of']))}" if auth else ""
        parts.append(f"[note {doc['id']}, {doc['date'] or 'undated'}, {doc['type']}, clinic: {doc['clinic'] or 'unknown'}, "
                     f"source: {src.group(1) if src else 'unknown'}{tag}] {excerpt}")
    out = "\n\n".join(parts)[:TOTAL_BUDGET]
    if family:
        out += "\n\nFAMILY REPORTS (the family's own knowledge; they count as support for what they state):\n" + "\n".join(f"- {f}" for f in family)
    return out


def norm_find(text, quote):
    """Index of a quote in a note, ignoring differences in whitespace (None if absent)."""
    if not quote:
        return None
    rx = r"\s+".join(re.escape(w) for w in quote.split())
    m = re.search(rx, text, re.I)
    return m.start() if m else None


UNREADABLE = {"verdict": "unreadable", "facts": 0, "supported": 0, "unsupported_facts": ["the local model's answer could not be read"]}


class Semantic:
    def __init__(self):
        from pipeline.config import load_config
        from pipeline.llm import require_local
        llm = load_config().get("llm", {})
        self.base, self.model = require_local(llm.get("url", "http://localhost:11434")), A.get("model") or llm.get("model", "qwen3:14b")
        self.cache = common.work_dir() / "audit_semantic"
        self.cache.mkdir(exist_ok=True)
        self.calls = self.hits = self.bad = 0
        self.ok = True

    def check(self, c, ev):
        prompt = SEM_PROMPT.format(claim=c["text"], evidence=ev)
        key = hashlib.sha256(f"{self.model}|{prompt}".encode()).hexdigest()[:24]
        f = self.cache / f"{key}.json"
        if f.exists():
            self.hits += 1
            cached = json.loads(f.read_text(encoding="utf-8"))
            return UNREADABLE if cached.get("unreadable") else verdict(cached)
        if not self.ok:
            return None
        body = {"model": self.model, "stream": False, "think": False, "format": SEM_SCHEMA,
                "messages": [{"role": "user", "content": prompt}], "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 1200}}
        out = None
        for attempt in range(2):   # a malformed answer (e.g. JSON cut off) is retried once, with more room
            try:
                req = urllib.request.Request(self.base + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=600) as r:
                    raw = json.loads(r.read())["message"]["content"]
            except (urllib.error.URLError, OSError):
                self.ok = False   # Ollama not running: the rest of the audit goes on without this check
                return None
            try:
                out = json.loads(raw)
                break
            except ValueError:
                body["options"]["num_predict"] = 2400
        self.calls += 1
        if out is None:   # cached too, so reruns don't re-ask; a changed claim or citation gets a fresh check
            self.bad += 1
            f.write_text(json.dumps({"unreadable": True}), encoding="utf-8")
            return UNREADABLE
        f.write_text(json.dumps(out), encoding="utf-8")
        return verdict(out)


# --- the audit -------------------------------------------------------------------------------------------------------
def load_sources():
    return (yaml.safe_load(SOURCES.read_text(encoding="utf-8")) or {}) if SOURCES.exists() else {}


def audit_claim(c, entry, docs, sem):
    srcs = (entry or {}).get("src", []) or []
    accept = (entry or {}).get("accept", {}) or {}
    doc_srcs = [s for s in srcs if "doc" in s]
    family = [s["family"] for s in srcs if "family" in s]
    r = {**c, "dates": [d for d, _ in c["dates"]], "cited": [], "family": family, "missing": [], "accepted": [], "problems": [],
         "searches": [], "semantic": None, "reviewed": (entry or {}).get("reviewed", "")}
    for s in srcs:   # {absent: pattern}: "not in the records" is checked by searching every published note
        if "absent" in s:
            rx = re.compile(s["absent"], re.I)
            hits = sorted(d["id"] for d in docs.values() if rx.search(d["text"]))
            r["searches"].append({"pattern": s["absent"], "notes": len(docs), "hits": hits})
            if hits:
                r["problems"].append(f"the records do mention it: {len(hits)} notes match /{s['absent']}/ ({', '.join(hits[:4])}{'…' if len(hits) > 4 else ''})")
    for s in doc_srcs:
        doc = docs.get(s["doc"])
        if not doc:
            r["problems"].append(f"note {s['doc']} is not in the published notes")
            continue
        quote = s.get("quote", "")
        found = norm_find(doc["text"], quote) is not None if quote else None
        if quote and not found:
            r["problems"].append(f"quote not found in note {s['doc']}")
        r["cited"].append({"doc": s["doc"], "date": doc["date"], "type": doc["type"], "clinic": doc["clinic"], "quote": quote, "quote_ok": found})
    good = [docs[s["doc"]] for s in doc_srcs if s["doc"] in docs]
    al = atoms(c)
    for kind, disp, test in (al if doc_srcs else []):   # a family report has no note to search
        if not any(test(d) for d in good):
            (r["accepted"] if disp in accept else r["missing"]).append(f"{disp}" + (f" (accepted: {accept[disp]})" if disp in accept else ""))
    if not srcs:
        r["status"] = "unsourced"
    elif r["problems"]:
        r["status"] = "broken"
    elif not doc_srcs and r["searches"] and not family:
        r["status"] = "grounded"
    elif not doc_srcs:
        r["status"] = "family"
    elif r["missing"]:
        r["status"] = "family" if family else "partial"
    else:
        r["status"] = "grounded"
    if sem and doc_srcs and not r["problems"]:
        r["semantic"] = sem.check(c, evidence(c, docs, [s for s in doc_srcs if s["doc"] in docs], al, family))
    return r


def derived():
    """Values the reports compute straight from the notes (no case-file claim to cite)."""
    out = []
    m = C.get("tumor_marker", {})
    if m.get("source"):
        f = next(C.notes.glob(m["source"]["glob"]), None)
        out.append(f"{m['name']} values ({len(C.marker)}): read from note {f.stem.rsplit('_', 1)[-1] if f else '(not found)'}.")
    elif m.get("values"):
        out.append(f"{m['name']} values ({len(m['values'])}): listed in the case file.")
    try:
        from . import labs
        _, used = labs.parse()
        if used:
            out.append(f"Blood counts: read from the lab tables of {used} notes (each value carries its draw date).")
    except Exception:
        pass
    wanted = C.get("reports") or []
    if not wanted or "vitals" in wanted:
        out.append("Weight, performance status and pain: read from the vital-sign lines of the visit notes (each point is a note date).")
    if not wanted or "medications" in wanted:
        out.append("Medication runs: read from the medication lists of the visit notes, plus the case's extra entries (audited above).")
    return out


AREA_ORDER = ["Treatments", "Treatments table", "Doses", "Side effects", "Pathology", "Imaging", "Events", "Implants", "Disease sites",
              "Treatment lines", "Medications", "Emergency summary", "Open questions", "Chart", "Narrative"]
STATUS = {"broken": ("Citation problem", "#b42318"), "partial": ("Partly grounded", "#b54708"), "unsourced": ("No source yet", "#6b7280"),
          "family": ("Family report", "#3b5bdb"), "grounded": ("Grounded", "#067647")}
ORDER = ["broken", "partial", "unsourced", "family", "grounded"]
SEM = {"supported": "model: supported", "partial": "model: partly supported", "unsupported": "model: not supported",
       "unreadable": "model: no usable answer"}


def run(semantic=True, log=print):
    docs = load_notes()
    sources = load_sources()
    claims = all_claims()
    sem = Semantic() if semantic else None
    results = [audit_claim(c, sources.get(c["key"]), docs, sem) for c in claims]
    stale = sorted(set(sources) - {c["key"] for c in claims})
    out = {"built": C.built, "notes": len(docs), "claims": results, "stale_keys": stale, "derived": derived(),
           "semantic_model": sem.model if sem else None, "semantic_ran": bool(sem and (sem.calls or sem.hits))}
    (common.work_dir() / "source_audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {s: sum(r["status"] == s for r in results) for s in ORDER}
    log(f"source audit: {len(results)} claims: " + ", ".join(f"{n} {STATUS[s][0].lower()}" for s, n in counts.items()))
    if sem:
        v = [r["semantic"]["verdict"] for r in results if r["semantic"]]
        log(f"source audit, local model ({sem.model}): {v.count('supported')} supported, {v.count('partial')} partly, "
            f"{v.count('unsupported')} not supported" + ("" if sem.ok else " (Ollama not reachable: some claims not checked)")
            + f"; {sem.calls} new checks, {sem.hits} cached" + (f", {sem.bad} unreadable answers" if sem.bad else ""))
    if stale:
        log(f"source audit: {len(stale)} entries in citations.yaml match no claim (renamed or removed)")
    return out


def appendix(out):
    res = out["claims"]
    counts = {s: sum(r["status"] == s for r in res) for s in ORDER}
    v = [r["semantic"]["verdict"] for r in res if r["semantic"]]
    chips = "".join(f'<span class="chip" style="border-color:{STATUS[s][1]};color:{STATUS[s][1]}">{STATUS[s][0]}: <b>{counts[s]}</b></span>' for s in ORDER)
    rows_by_area = {}
    for r in sorted(res, key=lambda r: (ORDER.index(r["status"]), r["area"])):
        rows_by_area.setdefault((ORDER.index(r["status"]) > 2, r["area"]), []).append(r)
    body = []
    def area_rank(area):   # the order a physician reads: treatment first, charts and narrative last
        return next((i for i, a in enumerate(AREA_ORDER) if area.startswith(a)), len(AREA_ORDER)), area

    for (done, area), rs in sorted(rows_by_area.items(), key=lambda kv: (kv[0][0], area_rank(kv[0][1]))):
        rows = []
        for r in rs:
            src = "".join(f'<div class="src"><b>{e(s["doc"])}</b> · {e(fmt(s["date"]) if s["date"] else "undated")} · {e(s["type"])}'
                          + (f' · <b class="rev">authoritative for {e(AUTHORITATIVE[s["doc"]]["covers"])}</b>' if s["doc"] in AUTHORITATIVE else "")
                          + (f'<br><q>{e(s["quote"][:260])}</q>' if s["quote"] else "") + ("" if s["quote_ok"] is not False else ' <b class="bad">(quote not found)</b>')
                          + "</div>" for s in r["cited"])
            src += "".join(f'<div class="src fam">Family report: {e(f)}</div>' for f in r["family"])
            src += "".join(f'<div class="src">Searched all {s["notes"]} notes for <q>{e(s["pattern"])}</q>: '
                           + (f'{len(s["hits"])} match' if s["hits"] else "no matches") + "</div>" for s in r.get("searches", []))
            notes = []
            if r["problems"]:
                notes.append('<b class="bad">' + e("; ".join(r["problems"])) + "</b>")
            if r["missing"]:
                notes.append("Not found in the cited notes: " + e(", ".join(r["missing"])))
            if r["accepted"]:
                notes.append("Accepted: " + e(", ".join(r["accepted"])))
            if r["semantic"]:
                sv = r["semantic"]
                notes.append(e(SEM[sv["verdict"]]) + f' ({sv.get("supported", 0)} of {sv.get("facts", 0)} facts)'
                             + ("; not supported: " + e("; ".join(sv["unsupported_facts"])[:300]) if sv.get("unsupported_facts") else ""))
            if r.get("reviewed"):
                notes.append('<b class="rev">Reviewed by hand:</b> ' + e(r["reviewed"]))
            st = STATUS[r["status"]]
            rows.append(f'<tr><td class="st" style="color:{st[1]}">{st[0]}</td><td><b>{e(r["label"])}</b><div class="claim">{e(r["text"][:420])}</div></td>'
                        f'<td>{src or "—"}</td><td class="nt">{"<br>".join(notes)}</td></tr>')
        body.append(f'<h2>{e(area)} <span class="n">{len(rs)}</span></h2><table><thead><tr><th style="width:13%">Status</th>'
                    f'<th style="width:37%">Claim</th><th style="width:30%">Source note and quote</th><th style="width:20%">Checks</th></tr></thead>'
                    f'<tbody>{"".join(rows)}</tbody></table>')
    derived_html = "".join(f"<li>{e(x)}</li>" for x in out["derived"])
    auth_html = "".join(f" <b>Authoritative:</b> note {e(d)} for {e(a['covers'])}, as of {e(fmt(str(a['as_of'])))}: {e(a.get('why', ''))}."
                        for d, a in AUTHORITATIVE.items())
    sem_line = (f"Local model ({e(out['semantic_model'])}) read each claim with its cited passages: {v.count('supported')} supported, "
                f"{v.count('partial')} partly, {v.count('unsupported')} not supported." if v else "The local-model reading was not run.")
    doc = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Source audit</title><style>{common.CSS}
@page {{ size: Letter landscape; margin: 9mm 9mm 10mm; }} body, .viz-root {{ background: #fff; }} .viz-root {{ padding: 0; font-size: 8.4pt; }}
.wrap {{ max-width: none; }} h1 {{ font-size: 15pt; margin: 0 0 1mm; }} h2 {{ font-size: 10.5pt; margin: 4mm 0 1mm; break-after: avoid; }}
h2 .n {{ color: var(--text-muted); font-weight: 400; }} .sub {{ color: var(--text-secondary); margin: 0 0 2mm; }}
.chip {{ display: inline-block; border: 1px solid; border-radius: 9px; padding: .4mm 2.2mm; margin: 0 1.5mm 1mm 0; font-size: 8pt; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 7.6pt; }} th {{ text-align: left; font-size: 7pt; text-transform: uppercase;
color: var(--text-secondary); border-bottom: 1.5px solid var(--text-secondary); padding: .8mm 1.2mm; }}
td {{ vertical-align: top; padding: 1mm 1.2mm; border-bottom: 1px solid var(--grid); line-height: 1.3; }} tr {{ break-inside: avoid; }}
td.st {{ font-weight: 700; }} .claim {{ color: var(--text-secondary); }} .src {{ margin-bottom: .8mm; }} .src q {{ color: var(--text-secondary); font-style: italic; }}
.fam {{ color: #3b5bdb; }} .rev {{ color: #067647; }} .bad {{ color: #b42318; }} .nt {{ color: var(--text-secondary); }} .method {{ columns: 2; column-gap: 8mm; font-size: 8pt; }}
.method p {{ margin: 0 0 1.5mm; }} .bottom {{ font-size: 9pt; margin: 1.5mm 0 2.5mm; }}</style></head><body><div class="viz-root"><div class="wrap">
<h1>Source audit: where each statement in the reports comes from</h1>
<p class="sub">{C.summary} · reports of {C.built} · {len(res)} statements checked against {out["notes"]} de-identified record notes.</p>
<div>{chips}</div>
<p class="bottom"><b>In short:</b> {counts["grounded"]} statements are grounded in a cited record note, {counts["family"]} rest on
family reports, and {counts["broken"] + counts["partial"] + counts["unsourced"]} need attention. Where the local model doubted a
statement, the checks column says what was then verified by hand.</p>
<div class="method"><p><b>What this is.</b> Every statement in the family's reports (each treatment, date, dose, scan, procedure, side effect,
emergency-card line and narrative paragraph) is listed here with the record note it comes from and a quote from that note. Note ids
refer to the de-identified record set; the family can produce the original document for any of them.</p>
<p><b>How it was checked.</b> Software confirmed that each cited note exists and contains the quoted words exactly, and that every
date, dose, drug or test name and clinician named in the statement appears in the cited notes. {sem_line} The model's reading is a second
opinion, not proof; "Family report" marks what the family supplied that the records do not contain.</p>
<p><b>How to read it.</b> Items that need attention come first (citation problems, details not found, statements without a source yet),
then family reports, then grounded statements.{auth_html} Values the reports compute directly from the notes:</p><ul>{derived_html}</ul></div>
{"".join(body)}</div></div></body></html>"""
    return common.write_and_print("source_audit", doc, f"source_audit_{C.built}.pdf")


# --- suggestions -----------------------------------------------------------------------------------------------------
STOP = set("about after again along also among before being below between both cancer could during each every first from have"
           " into later least more most never other over patient since some still such than that their then there these they"
           " this those through under until were when where which while with within would years".split())


def content_words(text):
    return {w for w in re.findall(r"[a-z][a-z\-]{4,}", norm(text)) if w not in STOP}


def best_line(doc, al, words):
    """The passage of a note that best shows a claim: most of its details (names, doses and terms count double, dates
    once) and most of its content words. Verbatim: one line, joined with the next when short."""
    body = doc["text"].split("\n---\n", 1)[-1] if doc["text"].startswith("---") else doc["text"]   # skip the front matter only
    lines = [l for l in body.splitlines() if l.strip()]
    best, score = "", -1
    for i, l in enumerate(lines):
        if l.startswith("## Page"):
            continue
        join = len(l) < 60 and i + 1 < len(lines) and not lines[i + 1].startswith("## Page")   # never across a page break
        chunk = l + " " + lines[i + 1] if join else l
        mini = {"norm": norm(chunk, markup=False), "text": chunk, **dict(zip(("days", "months"), doc_dates(chunk)))}
        sc = sum((1 if kind == "date" else 2) * test(mini) for kind, _, test in al) + len(words & content_words(chunk))
        if sc > score:
            best, score = chunk, sc
    best = re.sub(r"\s+", " ", best).strip()
    if len(best) > 240:   # keep the part with the most content words
        parts = [best[i:i + 240] for i in range(0, len(best) - 120, 120)]
        best = max(parts, key=lambda p: len(words & content_words(p)))
        best = best.split(" ", 1)[-1].rsplit(" ", 1)[0]
    return best


def line_score(doc, al, words):
    q = best_line(doc, al, words)
    mini = {"norm": norm(q, markup=False), "text": q, **dict(zip(("days", "months"), doc_dates(q)))}
    return sum((1 if k == "date" else 3) * t(mini) for k, _, t in al) + len(words & content_words(q)), q


def suggest(log=print, keys=None):
    """Propose sources for unsourced claims (or for ``keys``). A note qualifies by a claim's names, drugs, doses or
    content words, not by dates alone (a spreadsheet of dated rows "contains" any date); dates decide only on a note of
    the same day. Ties go to the note whose best passage shows most of the claim, then to the nearest date (or, for an
    undated claim such as a current medicine, the most recent note)."""
    docs = load_notes()
    sources = load_sources()
    out = {}
    for c in all_claims():
        if (keys is None and c["key"] in sources) or (keys is not None and c["key"] not in keys):
            continue
        al = atoms(c)
        words = content_words(c["text"])
        main = c["dates"][0][0] if c["dates"] else None
        dates_only = all(k == "date" for k, _, _ in al)
        scored = []
        for d in docs.values():
            hits = {i for i, (k, _, t) in enumerate(al) if t(d)}
            strong = {i for i in hits if al[i][0] != "date"}
            overlap = len(words & content_words(d["text"]))
            if dates_only and not (main and d["date"] == main) and not (hits and overlap >= 3):
                continue   # dates alone match any dated table; a same-day note, or the claim's own words, are needed too
            if not dates_only and not strong and overlap < 2:
                continue
            if not hits and overlap < 2:
                continue
            weight = 3 * len(strong) + len(hits - strong) + (3 if main and d["date"] == main else 0)
            scored.append([weight, hits, d, overlap])
        scored.sort(key=lambda x: (x[0], x[3]), reverse=True)
        shortlist = scored[:10]
        for x in shortlist:
            x.append(line_score(x[2], al, words))
        def when(d):
            if not d["date"]:
                return 0
            return -abs((date.fromisoformat(d["date"]) - date.fromisoformat(main)).days) if main else date.fromisoformat(d["date"]).toordinal()
        picked, covered = [], set()
        for _ in range(3):
            pool = [x for x in shortlist if x[2] not in [p[2] for p in picked]]
            if picked:
                pool = [x for x in pool if x[1] - covered]
            if not pool:
                break
            best = max(pool, key=lambda x: (len(x[1] - covered), x[4][0], when(x[2])))
            picked.append(best)
            covered |= best[1]
            if len(covered) == len(al):
                break
        entry = [{"doc": x[2]["id"], "quote": x[4][1]} for x in picked]
        if "family report" in c["text"].lower():
            entry.append({"family": "marked as a family report in the case"})
        if entry:
            out[c["key"]] = {"src": entry, "_coverage": f"{len(covered)}/{len(al)} details found"}
    SUGGESTED.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=140), encoding="utf-8")
    log(f"suggested sources for {len(out)} unsourced claims -> {SUGGESTED.name} (review before copying into {SOURCES.name})")


def main(semantic=True):
    out = run(semantic)
    pdf = appendix(out)
    print("built:", pdf.name)
    return out
