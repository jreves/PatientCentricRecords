"""Content-level duplicate detection across sources and formats.

The loader only skips byte-identical files. The same hospital episode also arrives as XML and
as a printed PDF, or re-exported on another day. Two documents are duplicates when the smaller
one's words are almost all contained in the larger, the two are of comparable size, and their
dates agree. The date guard matters: two clinic visits built from the same template (same med
list, allergies, problems) overlap heavily but are different visits.

Runs on raw text before LLM detection, so duplicates cost no LLM time. Reports doc ids only.
"""
import re
from collections import Counter

from . import chrono

FORMAT_PREFERENCE = {"xml": 0, "docx": 1, "pdf": 2, "txt": 3, "xlsx": 4}   # lower is kept
WORD = re.compile(r"[a-z]{3,}")


def fingerprint(doc):
    return Counter(WORD.findall("\n".join(doc.pages).lower()))


def doc_date(doc):
    if doc.kind == "xlsx":
        return None
    fmt = chrono.hospital_format(doc.pages)
    return fmt[0] if fmt else chrono.note_date(doc.pages)[0]


def episode_key(doc):
    """(start, end) of a C-CDA episode summary, from the XML reader's header or its PDF rendering."""
    fmt = chrono.hospital_format(doc.pages)
    if not fmt or not fmt[1].startswith("episode "):
        return None
    a, b = fmt[1][len("episode "):].split(" to ")
    return chrono.parse_date(a), chrono.parse_date(b)


def containment(small, large):
    total = sum(small.values())
    return sum(min(n, large[w]) for w, n in small.items()) / total if total else 0.0


def find_quotes(docs, cfg=None):
    """Small documents (e.g. a radiology report) whose text is quoted inside a larger one (an oncology note,
    a hospital summary). Not duplicates: the small one is the primary source and keeps its own entry. Returns
    {small doc_id: [larger doc_ids]} so the output can say "also quoted in"."""
    cfg = cfg or {}
    need = cfg.get("quote_containment", 0.9)
    window = cfg.get("quote_window_days", 60)
    fps = [fingerprint(d) for d in docs]
    sizes = [sum(f.values()) for f in fps]
    dates = [doc_date(d) for d in docs]
    out = {}
    for i, small in enumerate(docs):
        if small.kind == "xlsx" or not sizes[i] or sizes[i] > cfg.get("quote_max_words", 1500):
            continue
        for j, large in enumerate(docs):
            if j == i or large.kind == "xlsx" or sizes[j] < 2 * sizes[i]:
                continue
            if dates[i] and dates[j] and not (0 <= (dates[j] - dates[i]).days <= window):
                continue   # a note quotes a report on or after the report's date
            if containment(fps[i], fps[j]) >= need:
                out.setdefault(small.doc_id, []).append(large.doc_id)
    return out


def find_duplicates(docs, cfg=None):
    """-> (kept docs in original order, [(dropped_id, kept_id, score)])."""
    cfg = cfg or {}
    min_cont = cfg.get("min_containment", 0.85)
    strict = cfg.get("strict_containment", 0.95)     # when a date is missing on either side
    min_ratio = cfg.get("min_size_ratio", 0.5)
    fps = [fingerprint(d) for d in docs]
    sizes = [sum(f.values()) for f in fps]
    dates = [doc_date(d) for d in docs]
    episodes = [episode_key(d) for d in docs]
    parent = list(range(len(docs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    scores = {}
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            if not sizes[i] or not sizes[j] or docs[i].kind == "xlsx" or docs[j].kind == "xlsx":
                continue
            a, b = (i, j) if sizes[i] <= sizes[j] else (j, i)
            # An XML episode summary and a PDF with the same episode dates are the same export printed:
            # wording differs (the PDF lists empty template sections, the XML may carry more notes).
            if {docs[a].kind, docs[b].kind} == {"xml", "pdf"} and episodes[a] and episodes[a] == episodes[b]:
                parent[find(a)] = find(b)
                scores[(a, b)] = containment(fps[a], fps[b])
                continue
            if sizes[a] / sizes[b] < min_ratio:
                continue
            if dates[a] and dates[b] and abs((dates[a] - dates[b]).days) > 1:
                continue
            need = min_cont if dates[a] and dates[b] else strict
            score = containment(fps[a], fps[b])
            if score >= need:
                parent[find(a)] = find(b)
                scores[(a, b)] = score

    groups = {}
    for i in range(len(docs)):
        groups.setdefault(find(i), []).append(i)
    keep, dropped = set(), []
    for members in groups.values():
        best = min(members, key=lambda i: (FORMAT_PREFERENCE.get(docs[i].kind, 9), -sizes[i]))
        keep.add(best)
        for i in members:
            if i != best:
                s = scores.get((min(i, best, key=lambda k: sizes[k]), max(i, best, key=lambda k: sizes[k])))
                if s is None:   # linked through another member of the group
                    small, large = sorted((i, best), key=lambda k: sizes[k])
                    s = containment(fps[small], fps[large])
                dropped.append((docs[i].doc_id, docs[best].doc_id, s))
    return [d for k, d in enumerate(docs) if k in keep], dropped
