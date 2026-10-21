"""Leak check over de-identified output.

FAIL = a known identifier (from identifiers.toml or the registry) is still present.
WARN = something shaped like PII is present (phone, ID, "Dr. Smith", ...).
Console output is counts and doc ids only; matched text goes to private/verify_report.md.
"""
import re

from . import rules
from .names import Registry, parse_name

TOKEN_RE = re.compile(r"\[(?:PATIENT|CLINICIAN|PERSON|FACILITY|DOB|ID|PHONE|ADDRESS|LOCATION|EMAIL|URL|REDACTED)"
                      r"(?:-\d+)?(?:; age [\d+]+)?\]")
_P = {name: rx for name, rx, _ in rules.PATTERN_RULES + rules.NAME_RULES}
WARN_PATTERNS = [(n, _P[n]) for n in ("phone", "ssn", "email", "url", "labeled-id", "street", "long-number",
                                      "credential-name", "city-state", "city-state-zip", "state-zip-after-token",
                                      "id-next-line", "name-next-line")] + [
    ("bare-number-line", re.compile(r"^[ \t]*(?P<v>(?=(?:\D*\d){5})\d[\d\-]{3,18}\d)[ \t]*$", re.M)),   # one unlabelled number on a line
    ("dob-label", re.compile(rf"\b(?:DOB|Date[ \t]+of[ \t]+Birth)[ \t]*:?[ \t]*{rules.DATE}", re.I)),
    ("title-name", re.compile(rf"\b(?:Dr|Mr|Mrs|Ms|Miss)\.?[ \t]+{rules.NAME_WORD}")),
]


def _context(text, s, e):
    return text[max(0, s - 50):s].replace("\n", " ") + ">>" + text[s:e] + "<<" + text[e:e + 50].replace("\n", " ")


def verify_texts(texts, identifiers, registry_path, allow, policy=None, ocr_ids=()):
    """texts: {doc_id: text}. Returns (fail_hits, warn_hits) as [(check, doc_id, match, context)]."""
    registry = Registry(registry_path)
    denylist = rules.Denylist(identifiers)
    kept = rules.kept_categories(policy or {})
    from . import fuzzy
    fz_names, fz_digits = fuzzy.name_targets(registry, kept), fuzzy.digit_targets(identifiers)
    # Looser for the WARN pass: one more edit allowed for parts of 6+ letters.
    fz_loose = [(t, tok, c) for t, tok, c in fz_names if len(t) >= 6]
    known = [(rx, cap) for rx, _, cat, cap in registry.patterns(allow) if cat not in kept]
    warn_patterns = WARN_PATTERNS
    if "CLINICIAN" in kept:   # "Dr. X" and "X, MD" are expected in the output now
        warn_patterns = [(n, rx) for n, rx in WARN_PATTERNS if n not in ("credential-name", "title-name")]
        warn_patterns.append(("title-name", re.compile(rf"\b(?:Mr|Mrs|Ms|Miss)\.?[ \t]+{rules.NAME_WORD}")))
    fails, warns = [], []
    for doc_id, orig in texts.items():
        # Blank out our own tokens so e.g. "[ID]" can't match a name "ID"; offsets are preserved.
        text = TOKEN_RE.sub(lambda m: " " * len(m.group(0)), orig)
        for rx, cat in denylist.patterns:
            for m in rx.finditer(text):
                fails.append((f"identifier-{cat.lower()}", doc_id, m.group(0), _context(orig, m.start(), m.end())))
        for rx, cap in known:
            for m in rx.finditer(text):
                if not cap or m.group(0)[0].isupper():
                    fails.append(("known-name", doc_id, m.group(0), _context(orig, m.start(), m.end())))
        if doc_id in ocr_ids:
            for s, e, cat, _ in fuzzy.name_hits(text, fz_names, fuzzy.clinician_names(registry)) + fuzzy.number_hits(text, fz_digits):
                fails.append((f"ocr-fuzzy-{cat.lower()}", doc_id, orig[s:e], _context(orig, s, e)))
            for m in fuzzy.WORD.finditer(text):
                w = fuzzy.letters(m.group(0))
                # Capitalised words only: names in records are capitalised, and lowercase near-misses at the
                # normal distance are already a FAIL above; loose lowercase hits were ordinary words (2026-09-27).
                if len(w) >= 5 and m.group(0)[:1].isupper() and any(
                        fuzzy.within(w, t, fuzzy.max_dist(len(t)) + 1) for t, _, _ in fz_loose):
                    warns.append(("ocr-fuzzy-name-loose", doc_id, m.group(0), _context(orig, m.start(), m.end())))
        for name, rx in warn_patterns:
            # Two-line label checks look at the text with tokens intact: "PATIENT NAME: [PATIENT]" has its value
            # already, and blanking the token would make the next field look like its value (2026-09-28).
            src = orig if name.endswith("next-line") else text
            kept = rules.kept_ranges(src)
            for m in rx.finditer(src):
                if "[" in m.group(0) and not name.endswith("next-line"):
                    continue
                if any(a <= m.start("v") and m.end("v") <= b for a, b in kept) if "v" in rx.groupindex else False:
                    continue   # a model-level device identifier, kept on purpose
                if name == "credential-name" and parse_name(m.group("n")) is None:
                    continue  # credential stack after a redacted name, e.g. "[CLINICIAN-01] MSN, RN FNP-C"
                warns.append((name, doc_id, m.group(0), _context(orig, m.start(), m.end())))
    return fails, warns


def summarize(hits):
    by_check = {}
    for check, doc_id, _, _ in hits:
        n, docs = by_check.get(check, (0, set()))
        by_check[check] = (n + 1, docs | {doc_id})
    return by_check


def write_report(path, fails, warns):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Verify report (PRIVATE: contains raw identifiers)", ""]
    for title, hits in (("FAIL", fails), ("WARN", warns)):
        lines += [f"## {title}: {len(hits)}", ""]
        for check, doc_id, match, ctx in hits:
            lines.append(f"- `{check}` doc `{doc_id}`: `{match}`  \n  {ctx}")
        lines.append("")
    lines += ["Fix by adding to private/identifiers.toml (missed PII) or to the allowlist in",
              "config/local.toml (false positive), then rerun. If every WARN is harmless,",
              "rerun with --accept-warnings."]
    path.write_text("\n".join(lines), encoding="utf-8")
