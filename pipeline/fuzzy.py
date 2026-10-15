"""Fuzzy identifier matching for OCR'd text.

OCR misreads letters and digits ("Th0rnbury", "Margarel", "O4/l2/1961"), which defeats the
exact-match safeguards (identifiers.toml, registry propagation, the leak check). For OCR'd
documents only, this adds:
- names: each name part of the patient and of redacted people (not clinicians, who are kept)
  matched after undoing common OCR confusions, within an edit distance that grows with length
  (short parts must match exactly, to avoid hitting ordinary words);
- numbers: DOB variants, phones and IDs from identifiers.toml matched digit-for-digit after
  undoing letter-for-digit confusions.
"""
import re

from . import rules

TO_LETTERS = str.maketrans({"0": "o", "1": "l", "5": "s", "8": "b", "|": "l", "$": "s", "@": "a", "!": "l"})
TO_DIGITS = str.maketrans({"o": "0", "O": "0", "D": "0", "l": "1", "I": "1", "i": "1", "|": "1", "!": "1",
                           "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2"})
WORD = re.compile(r"[A-Za-z0-9|$@!][A-Za-z0-9|$@!'\-]*")
NUMERIC = re.compile(r"(?<![\w/])[0-9OoDlIi|!SsBZz][0-9OoDlIi|!SsBZz/.\-() ]{3,18}[0-9OoDlIi|!SsBZz](?![\w/])")


def max_dist(n):
    return 0 if n <= 4 else 1 if n <= 7 else 2


def letters(word):
    return re.sub(r"[^a-z]", "", word.lower().translate(TO_LETTERS))


def within(a, b, k):
    """Levenshtein distance <= k. Names are short, so a plain DP with an early exit is enough."""
    if abs(len(a) - len(b)) > k:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > k:
            return False
        prev = cur
    return prev[-1] <= k


def name_targets(registry, kept_cats=()):
    """[(normalised name part, token, cat)] for the patient and redacted people."""
    out = []
    for e in registry.entities:
        if e["cat"] not in ("PATIENT", "PERSON") or e["cat"] in kept_cats:
            continue
        parts = {p for f, l in e["names"] for p in (f, l) if p} | set(e.get("aliases", []))
        for p in parts:
            p = letters(p)
            if len(p) >= 3:
                out.append((p, registry.token(e), e["cat"]))
    return out


def digit_targets(identifiers):
    p = identifiers.get("patient", {})
    out = {}
    if p.get("dob"):
        for v in rules.date_variants(p["dob"]):
            d = re.sub(r"\D", "", v)
            if len(d) >= 5:
                out[d] = "DOB"
    ids, dob_like = rules.normalized_ids(identifiers)
    for v in ids:
        d = re.sub(r"\D", "", v)
        if len(d) >= 5:
            out[d] = "ID"
    for v in dob_like:
        d = re.sub(r"\D", "", v)
        if len(d) >= 5:
            out[d] = "DOB"
    for v in p.get("phones", []):
        d = re.sub(r"\D", "", v)[-10:]
        if len(d) == 10:
            out[d] = "PHONE"
            out[d[3:]] = "PHONE"   # without area code
    return out


def clinician_names(registry):
    """{(first, last)} of clinicians (whose names are kept), normalised like name parts."""
    return {(letters(f), letters(l)) for e in registry.entities if e["cat"] == "CLINICIAN"
            for f, l in e["names"] if f and l and len(letters(f)) >= 2 and len(letters(l)) >= 2}


def name_hits(text, targets, clinicians=()):
    """[(start, end, cat, token)] for words that are OCR-garbled forms of a target name part.

    A near miss that is exactly part of a known clinician's full name, written out beside the other part
    ("CHEN, LI", "Li Chen MD"), is that clinician, not a misread patient name (a clinician's surname can be one
    edit from a family name part). Exact matches of a target are always hits."""
    words = [(m.start(), m.end(), letters(m.group(0))) for m in WORD.finditer(text)]
    hits = []
    for i, (s, e, w) in enumerate(words):
        if len(w) < 3:
            continue
        for t, token, cat in targets:
            if within(w, t, max_dist(len(t))):
                if w != t and _in_clinician_name(text, words, i, clinicians):
                    break
                hits.append((s, e, cat, token))
                break
    return hits


# The full name must also be in a clinician's role: a credential after it, "Dr." before it, or a provider label
# earlier on the line. The registry's clinician/person split is a vote, so a name pair alone isn't enough.
CREDENTIAL_AFTER = re.compile(r"[ \t]*,?[ \t]*(?:MD|M\.D\.|DO|NP|PA-C|PA|APRN|FNP|RN|OD|PhD)\b")
TITLE_BEFORE = re.compile(r"\bDr\.?[ \t]*$", re.I)
PROVIDER_LABEL = re.compile(r"\b(?:Referring|Ordering|Attending|Consulting|Treating)[ \t]*(?:Provider|Physician|Doctor|MD)\b"
                            r"[^\n]*:|\bRequest[ \t]+of[ \t]*:", re.I)


def _in_clinician_name(text, words, i, clinicians):
    w = words[i][2]
    for j in (i - 1, i + 1):
        if 0 <= j < len(words):
            a, b = sorted((i, j))
            between = text[words[a][1]:words[b][0]]
            if re.fullmatch(r"[ \t]*,?[ \t]*", between):
                other = words[j][2]
                if (other, w) in clinicians or (w, other) in clinicians:
                    start, end = words[a][0], words[b][1]
                    line = text[text.rfind("\n", 0, start) + 1:start]
                    if (CREDENTIAL_AFTER.match(text, end) or TITLE_BEFORE.search(line)
                            or PROVIDER_LABEL.search(line)):
                        return True
    return False


def number_hits(text, targets):
    hits = []
    for m in NUMERIC.finditer(text):
        raw = m.group(0)
        if sum(c.isdigit() for c in raw) < 2:
            continue   # mostly letters: an ordinary word, not a misread number
        digits = re.sub(r"\D", "", raw.translate(TO_DIGITS))
        for d, cat in targets.items():
            if d and d in digits:
                hits.append((m.start(), m.end(), cat, rules_token(cat)))
                break
    return hits


def rules_token(cat):
    return {"DOB": "[DOB]", "ID": "[ID]", "PHONE": "[PHONE]"}[cat]
