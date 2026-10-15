"""Medication timeline: every drug on the medication lists at oncology visits, one bar per run of visits where it is listed,
grouped by purpose, plus medicines from other records (``medications.extra`` in the case). A current medication list the
family supplies can be made authoritative (``medications.current``): those continue to today, everything else ends at the
last visit that listed it."""
import html
import re
from datetime import date

from . import common, labs

e = html.escape
D = common.D
C = common.case()
M = C.get("medications", {})

# (name, group, pattern matched at the start of a medication-list line)
DEFAULT_CANON = [
    ("Ondansetron", "Nausea", r"(zofran \()?ondansetron"), ("Olanzapine", "Nausea", r"olanzapine"),
    ("Hydrocodone-acetaminophen", "Pain", r"hydrocodone"), ("Acetaminophen-codeine", "Pain", r"acetaminophen-codeine"),
    ("Acetaminophen (Tylenol)", "Pain", r"tylenol|acetaminophen oral"), ("Ibuprofen", "Pain", r"ibuprofen"),
    ("Meloxicam", "Pain", r"meloxicam"), ("Celecoxib", "Pain", r"celecoxib"), ("Medical cannabis", "Pain", r"cannabis"),
    ("Lidocaine 5% cream", "Pain", r"lidocaine topical cream 5"),
    ("Gabapentin", "Nerve pain (neuropathy)", r"gabapentin"), ("Duloxetine", "Nerve pain (neuropathy)", r"duloxetine"),
    ("Compounded nerve cream", "Nerve pain (neuropathy)", r"nerve cream"),
    ("\"Triple mix\" mouthwash", "Mouth sores", r"triple mix"), ("Dexamethasone mouthwash", "Mouth sores", r"dexamethasone oral liquid"),
    ("Omeprazole", "Stomach and bowel", r"omeprazole"), ("Diphenoxylate-atropine", "Stomach and bowel", r"diphenoxylate"),
    ("Cephalexin", "Infection", r"cephalexin"),
    ("Azithromycin eye drops", "Eyes", r"azithromycin ophthalmic"), ("Prednisolone 1% eye drops", "Eyes", r"prednisolone ophthalmic"),
    ("Carboxymethylcellulose eye drops", "Eyes", r"carboxymethylcellulose"), ("Refresh Relieva eye drops", "Eyes", r"refresh relieva"),
    ("Lidocaine-prilocaine (port)", "Other", r"lidocaine-prilocaine"), ("Benzonatate", "Other", r"benzonatate"),
    ("Portable oxygen (Boost)", "Other", r"miscellaneous drug misc .*oxygen"),
    ("Prenatal vitamin with iron", "Supplements", r"prenatal vitamins"), ("Ferrous sulfate", "Supplements", r"ferrous sulfate"),
    ("Omega-3", "Supplements", r"omega-3"), ("Probiotic (UltraFlora)", "Supplements", r"miscellaneous drug metagenics"),
    ("Ginseng", "Supplements", r"miscellaneous drug 1 ginseng"),
]
CANON = DEFAULT_CANON + [tuple(x) for x in M.get("canon_extra", [])]
# From other records than the visit lists: (name, group, start, end, ongoing, note)
EXTRA = [tuple(x) for x in M.get("extra", [])]
GROUPS = M.get("groups", ["Cancer treatment", "Bone", "Nausea", "Pain", "Nerve pain (neuropathy)", "Mouth sores", "Stomach and bowel",
                          "Infection", "Eyes", "Other", "Supplements"])
COLOR = {"Cancer treatment": "var(--series-2)", "Bone": "var(--series-4)", "Nausea": "var(--series-1)", "Pain": "var(--series-5)",
         "Nerve pain (neuropathy)": "var(--series-5)", "Mouth sores": "var(--series-1)", "Stomach and bowel": "var(--series-1)",
         "Infection": "var(--series-6)", "Eyes": "var(--series-3)", "Other": "var(--text-muted)", "Supplements": "var(--text-muted)"}
COLOR.update(M.get("colors", {}))
X0 = date.fromisoformat(M["start"]) if M.get("start") else None   # default: the earliest medicine start (see chart)
X1 = date.fromisoformat(M["end"]) if M.get("end") else common.year_end(C.today)
CURRENT = set(M.get("current", []))
NOTE_TYPES = M.get("note_types", r"_(oncology|palliative|treatment-review)")


def visit_lists():
    """[(iso date, [lines])] for every oncology / palliative visit note with a medication list."""
    out = []
    for f in sorted(labs.notes().glob("*.md")):
        if not re.search(NOTE_TYPES, f.name):
            continue
        text = f.read_text(encoding="utf-8")
        m = re.search(r"^Medications:\n(.*?)(?=^Medications reviewed|^Medications\*:|^Allergies)", text, re.M | re.S)
        if m:
            out.append((f.name[:10], [l.strip() for l in m.group(1).splitlines() if l.strip()]))
    return out


def runs(visits):
    """{name: [(first, last, listed count, latest dose line)]}: runs of visits where the drug is listed, bridging one missed visit."""
    dates = [d for d, _ in visits]
    res = {}
    for name, grp, pat in CANON:
        rx = re.compile(pat, re.I)
        hits = [any(rx.match(l) for l in lines) for _, lines in visits]
        dose = {d: next((l for l in lines if rx.match(l)), "") for d, lines in visits}
        rr, i = [], 0
        while i < len(hits):
            if not hits[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(hits) and (hits[j + 1] or (j + 2 < len(hits) and hits[j + 2])):
                j += 1
            while not hits[j]:
                j -= 1
            rr.append((dates[i], dates[j], sum(hits[i:j + 1]), dose[dates[j]]))
            i = j + 1
        if rr:
            res[name] = (grp, rr)
    return res, dates


def chart(res, dates):
    global X0
    if X0 is None:
        X0 = common.month_start(min([x[2] for x in EXTRA] + [rr[0][0] for _, rr in res.values()] + [dates[0]]))
    W, L, R = 1320, 250, 20
    x = lambda s: L + (W - L - R) * max(0, ((D(s) if isinstance(s, str) else s) - X0).days) / (X1 - X0).days
    rows = []
    for g in GROUPS:
        merged = {}
        for n, gg, a, b, ong, nt in EXTRA:
            if gg == g:
                merged.setdefault(n, []).append((a, b, None, None, ong, nt))
        for n, (gg, rr) in res.items():
            if gg == g:
                merged.setdefault(n, []).extend((a, b, c, dl, b == C.today, None) for a, b, c, dl in rr)
        items = [(n, sorted(sg)) for n, sg in merged.items()]
        items.sort(key=lambda it: it[1][0][0])
        if items:
            rows.append(("group", g, None))
            rows += [("drug", n, segs) for n, segs in items]
    s, y = [], 30
    # grid and the "no visit lists" shade
    shade1 = x(dates[0])
    for yr in range(X0.year + 1, X1.year + 1):
        xx = x(f"{yr}-01-01")
        s.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="22" y2="{{BOTTOM}}" stroke="var(--grid)"/>'
                 f'<text x="{xx + 4:.1f}" y="16" font-size="11" fill="var(--text-secondary)">{yr}</text>')
    shade0 = x(X0)
    s.append(f'<rect x="{shade0:.1f}" y="22" width="{shade1 - shade0:.1f}" height="{{SHADEH}}" fill="#f1f0ec" opacity="0.8"/>')
    s.append(f'<text x="{(shade0 + shade1) / 2:.1f}" y="40" text-anchor="middle" font-size="10" fill="var(--text-muted)">no visit medication lists before {dates[0][5:7].lstrip("0")}/{dates[0][:4]} '
             f'</text><text x="{(shade0 + shade1) / 2:.1f}" y="52" text-anchor="middle" font-size="10" fill="var(--text-muted)">(cancer and hospital drugs only)</text>')
    for kind, name, segs in rows:
        if kind == "group":
            y += 8
            s.append(f'<text x="12" y="{y + 11}" font-size="11" font-weight="700" fill="var(--text-primary)">{e(name.upper())}</text>'
                     f'<line x1="12" x2="{W - R}" y1="{y + 15}" y2="{y + 15}" stroke="var(--grid)"/>')
            y += 20
            grp = name
            continue
        s.append(f'<text x="{L - 8}" y="{y + 9}" text-anchor="end" font-size="10.5" fill="var(--text-primary)">{e(name)}</text>')
        for a, b, cnt, dl, ongoing, nt in segs:
            x0, x1 = x(a), max(x(b), x(a) + 3)
            s.append(f'<rect x="{x0:.1f}" y="{y + 1}" width="{x1 - x0:.1f}" height="10" rx="3" fill="{COLOR[grp]}"/>')
            if ongoing:
                s.append(f'<path d="M{x1 + 2:.1f},{y + 1} l7,5 l-7,5 z" fill="{COLOR[grp]}"/>')
        last = segs[-1]
        listed = sum(sg[2] or 0 for sg in segs)
        lab = next((sg[5] for sg in segs if sg[5]), "") if not last[2] else f"listed at {listed} visits"
        if last[2] and segs[0][5]:
            lab = f"{segs[0][5]}; listed at {listed} visits"
        lx = x(last[1]) + (12 if last[4] else 5)
        anc = "start"
        if lx > W - R - 150:
            lx, anc = x(segs[0][0]) - 5, "end"
            if lx < L + 120:
                lab = ""
        if lab:
            s.append(f'<text x="{lx:.1f}" y="{y + 9.5}" text-anchor="{anc}" font-size="9" fill="var(--text-secondary)">{e(lab)}</text>')
        y += 15
    svg = "".join(s).replace("{BOTTOM}", str(y)).replace("{SHADEH}", str(y - 22))
    return f'<svg viewBox="0 0 {W} {y + 8}" width="100%" role="img" aria-label="Medication timeline">{svg}</svg>', rows


def table(res):
    out = []
    for g in GROUPS:
        items = [(n, a, b, "", nt) for n, gg, a, b, ong, nt in EXTRA if gg == g]
        items += [(n, rr[0][0], rr[-1][1], f"{sum(r[2] for r in rr)} visits" + (f", {len(rr)} periods" if len(rr) > 1 else ""),
                   re.sub(r"\s+", " ", rr[-1][3])[:110]) for n, (gg, rr) in res.items() if gg == g]
        if not items:
            continue
        out.append(f'<tr class="grp"><td colspan="5">{e(g)}</td></tr>')
        for n, a, b, cnt, nt in sorted(items, key=lambda it: it[1]):
            out.append(f'<tr><td><b>{e(n)}</b></td><td class="n">{common.fmt(a)}</td><td class="n">{common.fmt(b)}</td><td class="n">{e(cnt)}</td><td>{e(nt)}</td></tr>')
    return ('<table class="meds"><thead><tr><th>Medicine</th><th>First</th><th>Last</th><th>Listed</th><th>Latest entry / note</th></tr></thead>'
            f'<tbody>{"".join(out)}</tbody></table>')


CSS = common.CSS + """
@page { size: Letter landscape; margin: 9mm 10mm 10mm; }
body, .viz-root { background: #fff; } .viz-root { padding: 0; font-size: 9pt; } .wrap { max-width: none; }
h1 { font-size: 15pt; margin: 0 0 1mm; } h2 { font-size: 12pt; margin: 0 0 1mm; border: 0; }
.sub { font-size: 8.4pt; color: var(--text-secondary); margin: 0 0 2mm; } .card { padding: 2mm; }
section.v + section.v { break-before: page; }
table.meds { font-size: 7.7pt; } table.meds td, table.meds th { padding: .6mm 1.4mm; } tr.grp td { background: #f1f0ec; font-weight: 700; }
.note { font-size: 7.6pt; color: var(--text-muted); margin-top: 2mm; }
.card svg { max-height: 150mm; width: auto; max-width: 100%; display: block; margin: 0 auto; } .card { break-inside: auto; }
"""


def main():
    visits = visit_lists()
    res, dates = runs(visits)
    for name in CURRENT & set(res):   # still taken: carry the last run to today
        grp, rr = res[name]
        a, b, c, dl = rr[-1]
        rr[-1] = (a, C.today, c, dl)
    svg, rows = chart(res, dates)
    n_drugs = sum(1 for k, *_ in rows if k == "drug")
    body = (f'<section class="v"><h1>{e(M["title"])}</h1>'
            f'<p class="sub">{C.text("medications_sub", n=n_drugs, visits=len(visits), first=common.fmt(dates[0]), last=common.fmt(dates[-1]))}</p>'
            f'<div class="card">{svg}</div></section>'
            f'<section class="v"><h2>Details</h2>{table(res)}<p class="note">{C.text("medications_note")}</p></section>')
    doc = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Medication timeline</title><style>{CSS}</style></head>'
           f'<body><div class="viz-root"><div class="wrap">{body}</div></div></body></html>')
    pdf = common.write_and_print("medications", doc, f"medication_timeline_{C.built}.pdf")
    print("built:", pdf.name, pdf.stat().st_size, "bytes;", len(visits), "visit lists;", n_drugs, "medicines")
    return pdf
