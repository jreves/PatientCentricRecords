"""Inventory of identifier values found in the raw sources (python -m pipeline ids).

Every ID-type detection (labelled IDs, IDs on their own or the next line, long numbers, LLM ID_NUMBER hits)
is grouped by the label in front of it (MRN, account, patient identifier, member/subscriber, accession...)
and by source. The console gets counts only; the values go to private/identifier_inventory.md so the USER can
copy the patient's record numbers into private/identifiers.toml [patient] ids. Listed ids become hard
leak-check FAILs everywhere, with fuzzy matching on OCR'd pages.
"""
import re
from collections import defaultdict

from . import rules
from .config import load_identifiers
from .dedup import find_duplicates
from .extract import load_documents
from .llm import OllamaNER
from .ocr import OCR

KINDS = [   # (kind, label regex checked against the text just before the value)
    ("MRN / medical record number", r"\bMRN\b|\bMR[ \t]*#|Med(?:ical)?[ \t]*Rec(?:ord)?|ARAMR"),
    ("Patient identifier", r"Patient[ \t]*(?:Identifier|ID)|\bPID\b|\bID[ \t]*#|Pt[ \t]*ID"),
    ("Account / encounter / FIN", r"\bAcct\b|Account|\bFIN\b|\bCSN\b|\bHAR\b|Enc(?:ounter)?[ \t]*(?:#|No|Number|ID)"),
    ("Insurance member / subscriber / policy / group", r"Member|Subscriber|Policy|Group[ \t]*(?:#|No|Number)|Insurance"),
    ("Accession / specimen / order / case", r"Accession|\bAcc[ \t]*#|Specimen|Order|Case|Req(?:uisition)?"),
    ("NPI / provider", r"\bNPI\b|Provider[ \t]*(?:ID|#)"),
    ("SSN", r"\bSSN\b|Social[ \t]*Security"),
]
KIND_RES = [(k, re.compile(rx, re.I)) for k, rx in KINDS]


def norm_id(v):
    return re.sub(r"\W", "", v).lower()


def classify(text, start):
    before = text[max(0, start - 60):start]
    before = before.split("\n")[-1] if before.split("\n")[-1].strip() else " ".join(before.split("\n")[-2:])
    for kind, rx in KIND_RES:
        if rx.search(before):
            return kind
    return "unlabelled (long number, LLM ID)"


def inventory(cfg, paths, log=print):
    identifiers = load_identifiers(paths)
    known = {norm_id(v) for v in identifiers.get("patient", {}).get("ids", [])}
    ocr = OCR(cfg.get("ocr", {}), paths.private / "cache" / "ocr") if any(s.get("ocr") for s in cfg["sources"]) else None
    docs, _ = load_documents(paths.root, cfg["sources"], ocr, paths.private / "cache" / "text")
    docs, _ = find_duplicates(docs, cfg.get("dedup", {}))   # same set the pipeline processes
    ner = OllamaNER(cfg["llm"], paths.cache) if cfg["llm"].get("enabled", True) else None
    den = rules.Denylist(identifiers)
    found = defaultdict(lambda: defaultdict(set))   # kind -> value -> {sources}
    uncached = 0
    for d in docs:
        for text in d.pages:
            spans = [(s.start, s.end) for s in rules.detect(text, den) if s.cat == "ID"]
            if ner:
                calls = ner.calls
                for surface, cat in ner.detect(text) or []:
                    if cat == "ID" and any(c.isdigit() for c in surface):
                        i = text.find(surface.strip())
                        if i >= 0:
                            spans.append((i, i + len(surface.strip())))
                uncached += ner.calls - calls
            for s, e in spans:
                v = text[s:e].strip()
                if sum(c.isdigit() for c in v) >= 4:
                    found[classify(text, s)][v].add(d.source)
    lines = ["# Identifier inventory (PRIVATE: contains raw identifier values)", "",
             "Every ID-type value the pipeline detected, by the label in front of it. All of these are already",
             "redacted wherever they were detected, and propagated corpus-wide. To make the patient's own record",
             "numbers a hard leak-check FAIL (and fuzzy-matched on OCR'd pages), copy them into",
             "private/identifiers.toml under [patient] ids. Values marked (listed) are already there.", ""]
    log(f"Identifier inventory ({uncached} uncached LLM calls):")
    for kind, _ in KINDS + [("unlabelled (long number, LLM ID)", None)]:
        vals = found.get(kind, {})
        if not vals:
            continue
        listed = sum(1 for v in vals if norm_id(v) in known)
        srcs = sorted({s for ss in vals.values() for s in ss})
        log(f"  {kind}: {len(vals)} distinct value(s), {listed} already in identifiers.toml; sources: {', '.join(srcs)}")
        lines += [f"## {kind}", "", "| Value | Sources | Listed |", "|---|---|---|"]
        for v in sorted(vals, key=lambda v: (-len(vals[v]), v)):
            lines.append(f"| {v} | {', '.join(sorted(vals[v]))} | {'yes' if norm_id(v) in known else ''} |")
        lines.append("")
    out = paths.private / "identifier_inventory.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    log("Wrote private/identifier_inventory.md for the USER to review.")
