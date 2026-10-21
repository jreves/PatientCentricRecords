"""Pipeline orchestration: extract -> detect -> build registry -> redact -> order -> verify -> publish.

Everything printed to the console is counts and doc ids only, never note text, because
the console output of this program is read by hosted Claude.
"""
import hashlib
import html
import json
import pathlib
import re
import shutil
from collections import Counter
from datetime import date, timedelta

from . import chrono, rules
from .config import PIPELINE_VERSION, load_identifiers
from .extract import load_documents
from . import fuzzy
from .llm import OllamaNER
from .ocr import OCR
from .names import Allowlist, Registry, trim_name_span
from .rules import NAME_CATS, Span
from .dedup import find_duplicates, find_quotes
from .sections import split_encounter

ID_SOURCES = {"labeled-id", "id-own-line", "id-next-line", "ssn", "denylist", "long-number"}
from .verify import summarize, verify_texts, write_report

FIXED_TOKENS = {"ADDRESS": "[ADDRESS]", "LOCATION": "[LOCATION]", "PHONE": "[PHONE]", "EMAIL": "[EMAIL]", "URL": "[URL]",
                "ID": "[ID]", "DOB": "[DOB]", "OTHER": "[REDACTED]"}
AGE_RE = re.compile(r"(?:age[:\s]*)?\d{1,3}(?:\s*(?:yo|y/o|y\.o\.|yrs?|years?(?:[- ]old)?|-year-old))?", re.I)
COLLAPSE = re.compile(r"(\[(?:PATIENT|[A-Z]+-\d+)\])(?:[ \t]*,?[ \t]+(?:[A-Z]\.?[ \t]+)?\1(?![\w-]))+")


def sanity_check(surface, cat):
    """The LLM's labels are unreliable: it has labelled drug and lab names PHONE/ID/URL.
    A surface that doesn't look like its category is dropped (None). Rerouting them to name
    handling was tried and turned ~2,000 clinical terms into "people" (HISTORY 2026-09-23).
    Real names are still caught by the rules, other chunks, and propagation."""
    digits = sum(c.isdigit() for c in surface)
    ok = {"PHONE": digits >= 7, "EMAIL": "@" in surface, "URL": "." in surface or "/" in surface,
          "ID": digits >= 1}.get(cat, True)
    return cat if ok else None


# UTF-8 punctuation that was decoded as cp1252 somewhere upstream (the portal's PDFs contain it).
MOJIBAKE = {"â€“": "–", "â€”": "—", "â€™": "’",
            "â€˜": "‘", "â€œ": "“", "â€": "”",
            "â€¢": "•", "â€¦": "…", "Â°": "°",
            "Â±": "±", "Â ": " "}


# pdfplumber: unmapped ligatures in some hospital PDFs, identified from context in the output
# ("Pa(cid:3)ent", "func(cid:13)on", "Le(cid:50)"). Font-specific, so only codes seen so far.
MOJIBAKE.update({"(cid:3)": "ti", "(cid:13)": "ti", "(cid:50)": "ft"})


def fix_mojibake(text):
    for bad, good in MOJIBAKE.items():
        text = text.replace(bad, good)
    return text


class PhaseClock:
    """Logs seconds per phase (no content)."""
    def __init__(self, log):
        import time
        self.time, self.log, self.t = time.perf_counter, log, time.perf_counter()

    def __call__(self, name):
        now = self.time()
        self.log(f"[timing] {name}: {now - self.t:.1f}s")
        self.t = now


def locate_llm(text, entities, allow):
    """Map LLM surfaces back to character spans. Surfaces not found verbatim are dropped."""
    spans, unlocated = [], 0
    for surface, cat in entities:
        surface = surface.strip()
        if len(surface) < 2 or allow.blocks(surface) or rules.DATE_RE.fullmatch(surface) or AGE_RE.fullmatch(surface):
            continue
        cat = sanity_check(surface, cat)
        if cat is None:
            continue
        if cat in NAME_CATS and not any(c.isupper() for c in surface):
            continue  # real names are capitalized; lowercase hits are ordinary words
        body = r"\s+".join(re.escape(w) for w in surface.split())
        pre = r"(?<![A-Za-z0-9])" if surface[0].isalnum() else ""
        post = r"(?![A-Za-z0-9])" if surface[-1].isalnum() else ""
        found = list(re.finditer(pre + body + post, text)) or list(re.finditer(pre + body + post, text, re.I))
        if not found:
            unlocated += 1
        for m in found:
            s, e = m.start(), m.end()
            if cat in NAME_CATS:
                s, e = trim_name_span(text, s, e)
            if e > s:
                spans.append(Span(s, e, cat, "llm"))
    return spans, unlocated


def assign_token(span, text, registry, policy):
    surface = text[span.start:span.end]
    if span.cat in NAME_CATS:
        entity = registry.resolve(surface, span.cat)
        if entity is None:
            return None
        if entity["cat"] == "CLINICIAN" and not policy.get("redact_clinicians", True):
            return None
        return registry.token(entity)
    if span.cat == "FACILITY":
        if not policy.get("redact_facilities", True):
            return None
        org = registry.org_for(surface)
        if org:
            return f"[{org['id']}]"
        entity = registry.resolve(surface, "PERSON")
        return registry.token(entity) if entity else "[FACILITY]"
    return FIXED_TOKENS.get(span.cat, "[REDACTED]")


def merge(spans):
    """Resolve overlaps: the union is redacted, labelled by its longest member."""
    out = []
    for s in sorted(spans, key=lambda s: (s.start, -(s.end - s.start))):
        if out and s.start < out[-1].end:
            last = out[-1]
            if (s.start, s.end) == (last.start, last.end) and s.cat == "DOB" and last.cat != "DOB":
                # The same text found as a DOB and as an ID (e.g. the DOB also listed under [patient] ids):
                # label it DOB so "[DOB; age N]" survives (2026-09-28).
                out[-1] = Span(last.start, last.end, "DOB", s.source, s.token)
                continue
            if s.end > last.end:
                win = s if (s.end - s.start) > (last.end - last.start) else last
                out[-1] = Span(last.start, s.end, win.cat, win.source, win.token)
            continue
        out.append(s)
    return out


def apply(text, spans):
    pieces, pos = [], 0
    for s in spans:
        pieces += [text[pos:s.start], s.token]
        pos = s.end
    pieces.append(text[pos:])
    return COLLAPSE.sub(r"\1", "".join(pieces))


def propagate(text, patterns):
    spans = []
    for rx, token, cat, need_cap in patterns:
        for m in rx.finditer(text):
            if need_cap and not m.group(0)[0].isupper():
                continue
            spans.append(Span(m.start(), m.end(), cat, "propagate", token))
    return spans


NARRATIVE = {"ed-provider-note", "hospital-h&p", "discharge-summary", "operative", "hospital-clinical-notes"}


def _entry(doc, rid, pages, numbers, page_counts, dob, d, basis, kind, clinic, clinical=True, section=None,
           encounter=None):
    age = chrono.age_at(dob, d)
    if age:
        pages = [pg.replace("[DOB]", f"[DOB; age {age}]") for pg in pages]
    counts = sum((page_counts[n - 1] for n in set(numbers)), Counter())
    return {"id": rid, "doc": doc, "pages": pages, "page_numbers": numbers, "counts": counts, "date": d,
            "basis": basis, "type": kind, "age": age, "clinic": clinic, "clinical": clinical, "section": section,
            "encounter": encounter}


def drop_textless(entries, doc):
    """policy.textless_pages = "drop": leave scanned pages out; an entry left empty disappears."""
    out = []
    for r in entries:
        keep = [(n, t) for n, t in zip(r["page_numbers"], r["pages"]) if n not in doc.textless_pages]
        if keep:
            r["page_numbers"], r["pages"] = [n for n, _ in keep], [t for _, t in keep]
            out.append(r)
    return out


MODALITIES = [   # (name, regex): first match in a report's opening text is its modality
    ("PET", r"\bPET\b|PET/CT|PET-CT"), ("bone scan", r"bone scan|nuclear medicine bone"),
    ("mammogram", r"mammo"), ("MRI", r"\bMRI?\b|\bMR\b|magnetic resonance"), ("CT", r"\bCTA?\b|computed tomography"),
    ("ultrasound", r"ultrasound|sonogra|\bUS\b"), ("x-ray", r"x-?ray|\bXR\b|radiograph"),
    ("DEXA", r"dexa|bone density"), ("echocardiogram", r"echocardio|\becho\b"), ("MUGA", r"\bmuga\b"),
]
MODALITY_RES = [(n, re.compile(rx, re.I)) for n, rx in MODALITIES]


def link_imaging(results):
    """Cross-reference each imaging report with the entries that cite the same exam: its modality
    within ~120 characters of its date ("PET scan [5/2/2024] = ..."). Notes summarise exams rather
    than paste them, so this finds the overlap that word containment can't (2026-09-28)."""
    for r in results:
        r["referenced_in"] = []
        if r["type"] != "imaging" or not r["date"]:
            continue
        head = "\n".join(r["pages"])[:800]
        hits = [(m.start(), n, rx) for n, rx in MODALITY_RES if (m := rx.search(head))]
        if not hits:
            continue
        _, name, rx = min(hits, key=lambda h: h[0])
        d = r["date"]
        forms = {f"{d.month}/{d.day}/{d.year}", f"{d.month:02}/{d.day:02}/{d.year}", f"{d.month}/{d.day}/{d.year % 100:02}",
                 f"{d.month:02}/{d.day:02}/{d.year % 100:02}", d.isoformat()}
        date_rx = re.compile(r"(?<![\d/])(?:" + "|".join(re.escape(f) for f in forms) + r")(?![\d/])")
        r["modality"] = name
        for o in results:
            if o is r or o["type"] == "spreadsheet" or o["doc"].doc_id == r["doc"].doc_id:
                continue
            text = "\n".join(o["pages"])
            if any(rx.search(text[max(0, m.start() - 120):m.end() + 120]) for m in date_rx.finditer(text)):
                r["referenced_in"].append(o["id"])


def describe(doc, pages, page_counts, dob):
    """One redacted document -> timeline entries: one per section for hospital encounter
    exports, otherwise one, dated and typed by the first rule family that recognises it."""
    numbers = list(range(1, len(pages) + 1))
    clinic = chrono.clinic(pages)
    if doc.kind in ("pdf", "txt") and (enc := split_encounter(pages, set(doc.textless_pages))):
        span = f"{enc.kind}, {enc.date} to {enc.discharge or enc.date}"
        out = []
        for k, sec in enumerate(enc.sections, 1):
            texts, nums = [t for _, t in sec.parts], [i + 1 for i in sec.pages]
            d, basis = enc.date, f"encounter start ({span})"
            if sec.type in NARRATIVE:   # a note's own date, if it falls inside the stay
                nd, nb = chrono.note_date(texts)
                end = enc.discharge or enc.date
                if nd and enc.date and end and (enc.date - timedelta(days=1)) <= nd <= (end + timedelta(days=1)):
                    d, basis = nd, nb
            out.append(_entry(doc, f"{doc.doc_id}-s{k:02}", texts, nums, page_counts, dob, d, basis, sec.type,
                              clinic, sec.clinical, sec.title, span))
        return out
    if fmt := chrono.hospital_format(pages):
        d, basis, kind = fmt
    elif doc.kind == "xlsx":
        d, basis = chrono.table_dates(pages)
        kind = chrono.note_type(pages, doc.kind)
    else:
        d, basis = chrono.note_date(pages)
        kind = chrono.note_type(pages, doc.kind)
    return [_entry(doc, doc.doc_id, pages, numbers, page_counts, dob, d, basis, kind, clinic)]


def run(cfg, paths, use_llm=True, accept_warnings=False, limit=None, log=print):
    identifiers = load_identifiers(paths)
    if not identifiers:
        log("NOTE: private/identifiers.toml is missing or empty; relying on rules + LLM only.")
    raw_ids = identifiers.get("patient", {}).get("ids", [])
    ids_norm, ids_dates = rules.normalized_ids(identifiers)
    relabelled = sum(1 for v in raw_ids if rules.ID_LABEL_PREFIX.match(v.strip()))
    if relabelled or ids_dates:
        log(f"identifiers.toml [patient] ids: {relabelled} entr(ies) had a label prefix (value used), "
            f"{len(ids_dates)} are dates (handled as DOB)")
    allow = Allowlist(cfg)
    policy = cfg.get("policy", {})
    denylist = rules.Denylist(identifiers)
    clock = PhaseClock(log)
    ocr = OCR(cfg.get("ocr", {}), paths.private / "cache" / "ocr") if any(s.get("ocr") for s in cfg["sources"]) else None
    docs, stats = load_documents(paths.root, cfg["sources"], ocr, paths.private / "cache" / "text")
    clock("load + OCR")
    if ocr:
        ocrd = [c for d in docs for c in d.ocr_pages.values()]
        log(f"OCR: {len(ocrd)} page(s) in {sum(1 for d in docs if d.ocr_pages)} doc(s) "
            f"({ocr.pages_done} new, {ocr.cache_hits} cached); mean confidence "
            f"{sum(ocrd) / len(ocrd) if ocrd else 0:.0f}, {sum(c < 60 for c in ocrd)} page(s) below 60")
    if limit:
        docs = docs[:limit]
    docs, dups = find_duplicates(docs, cfg.get("dedup", {}))
    if dups:
        log(f"Content duplicates skipped: {len(dups)} ("
            + "; ".join(f"{a} = {b}, {s:.0%} contained" for a, b, s in dups) + ")")
    paths.private.mkdir(parents=True, exist_ok=True)
    (paths.private / "duplicates.json").write_text(json.dumps(
        [{"dropped": a, "kept": b, "containment": round(s, 3)} for a, b, s in dups], indent=1), encoding="utf-8")
    by_doc_id = {d.doc_id: d for d in docs}
    quotes = find_quotes(docs, cfg.get("dedup", {}))
    clock("dedup + quote search")
    if quotes:
        log(f"Also quoted inside larger documents (kept, cross-referenced): {len(quotes)} doc(s)")
    log(f"Loaded {len(docs)} documents, {sum(len(d.pages) for d in docs)} pages "
        f"(skipped: {stats['unsupported']} unsupported, {stats['duplicates']} duplicates)")
    textless = {d.doc_id: d.textless_pages for d in docs if d.textless_pages}
    drop_scans = policy.get("textless_pages", "mark") == "drop"
    if textless:
        what = "dropped (policy.textless_pages = drop)" if drop_scans else "marked, text not included (no OCR)"
        log(f"Pages with no text layer (scanned images): {sum(map(len, textless.values()))} in "
            f"{len(textless)} doc(s), {what}: {', '.join(sorted(textless))}")
        # A document with no text at all is lost entirely: say where it is, so OCR can be turned on for that source.
        for d in docs:
            if d.textless_pages and len(d.textless_pages) == len(d.pages):
                log(f"  {d.doc_id}: all {len(d.pages)} page(s) are scans with no text (source '{d.source}'); "
                    f"set ocr = true for that source to read it")

    ner = OllamaNER(cfg["llm"], paths.cache) if use_llm and cfg["llm"].get("enabled", True) else None
    if ner:
        log(f"LLM detection: {ner.model} (local Ollama; contacted only for text not in the cache)")
    else:
        log("LLM detection: DISABLED (rules and identifiers only; output is not publishable)")

    # Phase 1: detect on every page and collect name mentions.
    detected, mentions, failed_docs, unlocated, kept_values = {}, [], set(), 0, set()
    for i, doc in enumerate(docs, 1):
        for p, text in enumerate(doc.pages):
            spans = rules.detect(text, denylist)
            spans = [Span(*trim_name_span(text, s.start, s.end), s.cat, s.source) if s.cat in NAME_CATS else s
                     for s in spans]
            if ner:
                ents = ner.detect(text)
                if ents is None:
                    failed_docs.add(doc.doc_id)
                    ents = []
                llm_spans, missing = locate_llm(text, ents, allow)
                spans += llm_spans
                unlocated += missing
            kept = rules.kept_ranges(text)   # model-level device identifiers and catalog numbers stay readable
            # any non-name label: the local model's type labels are unreliable (it may call a catalog number OTHER)
            spans = [s for s in spans if s.end > s.start
                     and not (s.cat not in NAME_CATS and any(a <= s.start and s.end <= b for a, b in kept))]
            kept_values.update(text[a:b] for a, b in kept)
            detected[(doc.doc_id, p)] = spans
            mentions += [(text[s.start:s.end], s.cat) for s in spans if s.cat in NAME_CATS | {"FACILITY"}]
        extra = f", LLM calls {ner.calls} / cached {ner.cache_hits}" if ner else ""
        log(f"  [{i}/{len(docs)}] {doc.doc_id}: {len(doc.pages)} pages{extra}", flush=True)

    clock("phase 1: rules + LLM detection")
    registry = Registry(paths.registry)
    registry.build(mentions, identifiers, allow)
    registry.save()
    patterns = [p for p in registry.patterns(allow) if p[2] not in rules.kept_categories(policy)]
    # IDs found by a rule anywhere are redacted everywhere, like names: an ID printed unlabelled
    # in one document (e.g. on its own line) is often labelled in another.
    corpus_ids = {doc.pages[p][s.start:s.end] for (doc_id, p), spans in detected.items()
                  for doc in [by_doc_id[doc_id]] for s in spans
                  if s.cat == "ID" and s.source in ID_SOURCES}
    corpus_ids = {v for v in corpus_ids if len(v) >= 6 and any(c.isdigit() for c in v) and v not in kept_values}
    if corpus_ids:   # one alternation (longest first): a pattern per ID made each page ~1,000 scans (2026-09-28)
        alt = "|".join(re.escape(v) for v in sorted(corpus_ids, key=len, reverse=True))
        patterns.append((re.compile(rf"(?<![\w-])(?:{alt})(?![\w-])"), "[ID]", "ID", False))
    fz_names = fuzzy.name_targets(registry, rules.kept_categories(policy))
    fz_digits = fuzzy.digit_targets(identifiers)
    fz_clin = fuzzy.clinician_names(registry)
    ents = Counter(e["cat"] for e in registry.entities)
    log(f"Registry: patient {'identified' if registry.patient else 'NOT identified'}; "
        f"{ents['CLINICIAN']} clinicians, {ents['PERSON']} other people, {len(registry.orgs)} organizations")

    clock("registry + patterns")
    # Phase 2: redact.
    known_dob = chrono.parse_date(identifiers.get("patient", {}).get("dob", "") or "", earliest=1900)
    results, totals = [], Counter()
    for doc in docs:
        red_pages, page_counts, dobs = [], [], []
        for p, text in enumerate(doc.pages):
            spans = []
            for s in detected[(doc.doc_id, p)]:
                s.token = assign_token(s, text, registry, policy)
                if s.token:
                    spans.append(s)
            spans += propagate(text, patterns)
            if doc.ocr_pages:   # OCR misreads letters: catch garbled forms of known names and numbers
                # Judge the clinician-name exemption on the text as it will be published (redactions blanked, as the
                # leak check sees it): a near miss beside a word that is itself redacted is not spared. Repeat until
                # stable, since a new fuzzy hit can be the neighbour another near miss relied on.
                hits = []
                for _ in range(4):
                    blank = list(text)
                    for s in spans + [Span(a, b, c, "fuzzy", t) for a, b, c, t in hits]:
                        blank[s.start:s.end] = " " * (s.end - s.start)
                    new = fuzzy.name_hits("".join(blank), fz_names, fz_clin)
                    new = [h for h in new if h not in hits]
                    if not new:
                        break
                    hits += new
                spans += [Span(s, e, cat, "fuzzy", tok) for s, e, cat, tok in hits + fuzzy.number_hits(text, fz_digits)]
            spans = merge(spans)
            page_counts.append(Counter(s.cat for s in spans))
            dobs += [dob for s in spans if s.cat == "DOB" and (dob := chrono.parse_date(text[s.start:s.end], earliest=1900))]
            red_pages.append(fix_mojibake(apply(text, spans)))
            detected[(doc.doc_id, p)] = spans
        totals.update(sum(page_counts, Counter()))
        entries = describe(doc, red_pages, page_counts, known_dob or (dobs[0] if dobs else None))
        results += drop_textless(entries, doc) if drop_scans else entries
    log("Redactions: " + ", ".join(f"{k} {v}" for k, v in sorted(totals.items())))
    if unlocated:
        log(f"LLM surfaces not found verbatim in text (ignored): {unlocated}")
    split = [r for r in results if r["section"]]
    if split:
        log(f"Encounter exports split into sections: {len({r['doc'].doc_id for r in split})} doc(s) -> "
            f"{len(split)} sections ({sum(r['clinical'] for r in split)} clinical)")

    for r in results:
        r["quoted_in"] = quotes.get(r["doc"].doc_id, [])
    clock("phase 2: redact + describe")
    link_imaging(results)
    clock("imaging cross-references")
    linked = [r for r in results if r["referenced_in"]]
    if linked:
        log(f"Imaging reports cited in other entries: {len(linked)} of {sum(r['type'] == 'imaging' for r in results)} "
            f"({sum(len(r['referenced_in']) for r in linked)} citations)")
    results.sort(key=lambda r: (r["date"] or date.max, r["id"]))
    write_output(paths.staging, results, cfg, legend(policy))
    write_review(paths.review, docs, detected, results)
    clock("write output + review")
    (paths.private / "source_map.json").write_text(json.dumps(
        {r["doc"].doc_id: {"source": r["doc"].source, "file": r["doc"].filename} for r in results}, indent=1),
        encoding="utf-8")

    # Verify, then publish only if clean.
    texts = {r["id"]: "\n".join(r["pages"]) for r in results}   # every section is checked
    assert len(texts) == len(results), "result ids must be unique, or sections would skip the leak check"
    ocr_ids = {r["id"] for r in results if r["doc"].ocr_pages}
    fails, warns = verify_texts(texts, identifiers, paths.registry, allow, policy, ocr_ids)
    write_report(paths.private / "verify_report.md", fails, warns)
    report_hits(fails, warns, log)
    clock("verify")
    # --accept-warnings accepts exactly the warnings shown in this run (check, entry, match and context),
    # and remembers them; a new or changed warning blocks again until the user has reviewed it.
    acc_path = paths.private / "accepted_warnings.json"
    accepted = set(json.loads(acc_path.read_text(encoding="utf-8"))) if acc_path.exists() else set()
    wkey = lambda w: hashlib.sha256("|".join(w).encode("utf-8")).hexdigest()
    if accept_warnings and warns:
        accepted |= {wkey(w) for w in warns}
        acc_path.write_text(json.dumps(sorted(accepted), indent=1), encoding="utf-8")
    pending = [w for w in warns if wkey(w) not in accepted]
    if warns:
        log(f"Warnings: {len(warns) - len(pending)} accepted after review, {len(pending)} not yet reviewed")
    blockers = []
    if fails:
        blockers.append(f"{len(fails)} known-identifier leak(s)")
    if pending:
        blockers.append(f"{len(pending)} warning(s) not yet reviewed")
    if failed_docs:
        blockers.append(f"LLM failed on {len(failed_docs)} doc(s): {', '.join(sorted(failed_docs))}")
    if not ner:
        blockers.append("LLM detection was disabled")
    if blockers:
        log("NOT PUBLISHED: " + "; ".join(blockers) + ".")
        log("Review private/verify_report.md and private/review/index.html locally (Claude must not read them).")
        return False
    publish(paths)
    log(f"PUBLISHED {len(results)} notes to '{paths.output.name}/'.")
    return True


def report_hits(fails, warns, log):
    for label, hits in (("FAIL", fails), ("WARN", warns)):
        summary = summarize(hits)
        log(f"Verify {label}: {len(hits)}" + "".join(
            f"\n  {check}: {n} hit(s) in doc(s) {', '.join(sorted(docs))}" for check, (n, docs) in summary.items()))


class PublishError(RuntimeError):
    pass


def publish(paths):
    """Replace the output's files in place. Folders are kept, since Windows won't delete a
    folder that is open in Explorer."""
    out = paths.output
    out.mkdir(exist_ok=True)
    try:
        for f in sorted(out.rglob("*"), reverse=True):
            if f.is_file():
                f.unlink()
        shutil.copytree(paths.staging, out, dirs_exist_ok=True)
        readme = pathlib.Path(__file__).resolve().parent / "folders" / "filtered.md"
        if readme.exists():
            shutil.copy(readme, out / "README.md")
    except PermissionError as e:
        name = pathlib.Path(e.filename).name if e.filename else "a file"
        raise PublishError(f"could not replace '{name}' in the output folder; close it in any editor and rerun") from None


# --- writers -----------------------------------------------------------------------
def legend(policy):
    kept = rules.kept_categories(policy)
    names = []
    names.append("Clinician names are kept as written." if "CLINICIAN" in kept
                 else "[CLINICIAN-nn] = the same clinician everywhere.")
    names.append("Hospital/practice names are kept as written." if "FACILITY" in kept
                 else "[FACILITY-nn] = the same organization everywhere.")
    return ("Tokens: [PATIENT] = the patient. [PERSON-nn] = the same non-clinician person (family, contacts)\n"
            f"everywhere; numbering is stable across runs. {' '.join(names)}\n" + LEGEND)


LEGEND = """[DOB] [ID] [PHONE] [ADDRESS] [EMAIL] [URL] [REDACTED] = removed identifiers. Clinical dates are
real; the note date and how it was chosen are in each note's header. Date of birth is removed;
[DOB; age N] and patient_age give her age on the note date instead."""


def _name(r):
    d = r["date"].isoformat() if r["date"] else "undated"
    return f"{d}_{r['type']}_{r['id']}.md"


def ocr_of(r):
    return {n: r["doc"].ocr_pages[n] for n in r["page_numbers"] if n in r["doc"].ocr_pages}


def _note_md(r):
    doc = r["doc"]
    head = ["---", f"doc_id: {r['id']}", f"date: {r['date'] or 'unknown'}", f"date_basis: \"{r['basis']}\"",
            f"type: {r['type']}", f"clinic: {r['clinic'] or 'unknown'}", f"patient_age: {r['age'] or 'unknown'}"]
    if r["section"]:
        head += [f"parent_doc: {doc.doc_id}", f"section: \"{r['section']}\"", f"encounter: \"{r['encounter']}\"",
                 f"clinical: {str(r['clinical']).lower()}"]
    head += [f"source: {doc.source}", f"format: {doc.kind}",
             f"pages: {r['page_numbers'][0]}-{r['page_numbers'][-1]} of {len(doc.pages)}" if r["section"]
             else f"pages: {len(r['pages'])}",
             f"pages_without_text: {[n for n in r['page_numbers'] if n in doc.textless_pages]}",
             *([f"ocr_pages: {ocr_of(r)}  # page: Tesseract mean confidence 0-100"] if ocr_of(r) else []),
             *([f"also_quoted_in: {r['quoted_in']}  # parent doc ids that quote this document"] if r.get("quoted_in") else []),
             *([f"modality: {r['modality']}"] if r.get("modality") else []),
             *([f"cited_in: {r['referenced_in']}  # entries that mention this exam (modality + date)"] if r.get("referenced_in") else []),
             f"redactions: {sum(r['counts'].values())}", f"pipeline_version: {PIPELINE_VERSION}", "---", ""]
    body = []
    for n, page in zip(r["page_numbers"], r["pages"]):
        if n in doc.textless_pages:
            page = "[no text layer: scanned image, not included]"
        body += [f"## Page {n}", "", page, ""]
    return "\n".join(head + body)


def write_output(staging, results, cfg, legend_text):
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "notes").mkdir(parents=True)
    manifest, rows = [], []
    clinical = ["# Clinical notes, chronological (de-identified)", "",
                "Clinical content only: hospital orders, flowsheets, medication administration records, care plans "
                "and administrative pages are left out (see all_documents_chronological.md).", "", legend_text, ""]
    full = ["# All documents, chronological (de-identified)", "", legend_text, ""]
    for r in results:
        name = _name(r)
        md = _note_md(r)
        (staging / "notes" / name).write_text(md, encoding="utf-8")
        low = "" if r["basis"].startswith(("label", "spreadsheet", "episode", "appointment", "encounter")) \
            or " dated " in r["basis"] or r["basis"].startswith("portal") else " ⚠"
        what = f"{r['type']} ({r['section']})" if r["section"] else r["type"]
        rows.append(f"| {r['date'] or '?'}{low} | {r['age'] or ''} | {what} | {r['clinic'] or ''} | "
                    f"{len(r['pages'])} | [{r['id']}](notes/{name}) |")
        block = [f"\n# {r['date'] or 'undated'} | {what} | doc {r['id']}", "", md.split("---\n", 2)[2]]
        full += block
        if r["clinical"]:
            clinical += block
        manifest.append({"doc_id": r["id"], "parent_doc": r["doc"].doc_id, "date": str(r["date"] or ""),
                         "date_basis": r["basis"], "type": r["type"], "section": r["section"],
                         "encounter": r["encounter"], "clinical": r["clinical"], "clinic": r["clinic"],
                         "patient_age": r["age"], "source": r["doc"].source, "format": r["doc"].kind,
                         "pages": r["page_numbers"],
                         "pages_without_text": [n for n in r["page_numbers"] if n in r["doc"].textless_pages],
                         "ocr_pages": ocr_of(r), "quoted_in": r.get("quoted_in", []),
                         "modality": r.get("modality"), "cited_in": r.get("referenced_in", []),
                         "redactions": dict(r["counts"]), "file": f"notes/{name}"})
    timeline = ["# Timeline", "", f"{len(results)} documents, pipeline {PIPELINE_VERSION}. "
                "⚠ = date not taken from a labelled field; check it.", "",
                "| Date | Age | Type | Clinic | Pages | Note |", "|---|---|---|---|---|---|", *rows]
    (staging / "timeline.md").write_text("\n".join(timeline) + "\n", encoding="utf-8")
    (staging / "all_notes_chronological.md").write_text("\n".join(clinical), encoding="utf-8")
    (staging / "all_documents_chronological.md").write_text("\n".join(full), encoding="utf-8")
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (staging / "README.md").write_text(
        "# Filtered (de-identified) notes\n\nGenerated by the local de-identification pipeline; do not edit by hand, "
        "rerun `python -m pipeline run`.\n\n" + legend_text + "\n\n- `timeline.md`: index by date\n"
        "- `notes/`: one file per document; hospital encounter exports are split into one file per section\n"
        "- `all_notes_chronological.md`: clinical content in one file, for loading into a long-context session\n"
        "- `all_documents_chronological.md`: everything, including orders/flowsheets/administrative sections\n",
        encoding="utf-8")


def write_review(review_dir, docs, detected, results):
    """Local-only HTML showing each original page with its redactions highlighted."""
    # Empty it rather than delete it: the user often has it open in Explorer or a browser, which locks the folder.
    review_dir.mkdir(parents=True, exist_ok=True)
    for p in review_dir.iterdir():
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    style = ("<style>body{font:14px/1.5 system-ui;margin:2em;max-width:70em}pre{white-space:pre-wrap;"
             "background:#f7f7f7;padding:1em}mark{background:#ffd54f}mark.n{background:#ef9a9a}"
             "mark.f{background:#90caf9}</style>")
    by_doc = {}
    for r in results:
        by_doc.setdefault(r["doc"].doc_id, []).append(r)
    index = [f"<html><head><meta charset='utf-8'><title>Redaction review</title>{style}</head><body>",
             "<h1>Redaction review (PRIVATE)</h1><p>Red = names, blue = organizations, yellow = other.</p><ul>"]
    for doc in docs:
        entries = by_doc.get(doc.doc_id)
        if not entries:   # every page was a scan with no text and was dropped: nothing to review
            continue
        first = min(entries, key=lambda r: (r["date"] or date.max))
        label = f"{first['date']} {first['type'] if len(entries) == 1 else f'encounter, {len(entries)} sections'}"
        n_redactions = sum(len(detected[(doc.doc_id, p)]) for p in range(len(doc.pages)))
        parts = [f"<html><head><meta charset='utf-8'><title>{doc.doc_id}</title>{style}</head><body>",
                 f"<p><a href='index.html'>index</a></p><h1>{doc.doc_id}: {label}</h1>"]
        for p, text in enumerate(doc.pages):
            out, pos = [], 0
            for s in detected[(doc.doc_id, p)]:
                cls = "n" if s.cat in NAME_CATS else "f" if s.cat == "FACILITY" else ""
                out += [html.escape(text[pos:s.start]),
                        f"<mark class='{cls}' title='{s.cat} via {s.source} -> {html.escape(s.token)}'>"
                        f"{html.escape(text[s.start:s.end])}</mark>"]
                pos = s.end
            out.append(html.escape(text[pos:]))
            parts.append(f"<h2>Page {p + 1}</h2><pre>{''.join(out)}</pre>")
        (review_dir / f"{doc.doc_id}.html").write_text("".join(parts) + "</body></html>", encoding="utf-8")
        index.append(f"<li><a href='{doc.doc_id}.html'>{label} {doc.doc_id}</a> ({n_redactions} redactions)</li>")
    (review_dir / "index.html").write_text("".join(index) + "</ul></body></html>", encoding="utf-8")
