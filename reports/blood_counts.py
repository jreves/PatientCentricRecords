"""Blood counts (WBC, ANC, hemoglobin, platelets) over time, with chemotherapy dose levels above them.
Values come from the published notes' lab tables (labs.py); dose levels and events from the case file (``blood_counts:``)."""
import html
from datetime import date

from . import common, labs

e = html.escape
D = common.D
C = common.case()
BC = C.get("blood_counts", {})

# Typical adult ranges, set to agree with the lab's own H/L flags (override in the case: blood_counts.panels).
PANELS = [tuple(p) for p in BC.get("panels", [
    ["WBC", "White blood cells", "×10³/µL", 4.5, 11.0, []],
    ["ANC", "Neutrophils (ANC)", "×10³/µL", 1.5, 7.5, [[1.0, "grade 3 below 1.0"], [0.5, "grade 4 below 0.5"]]],
    ["HGB", "Hemoglobin", "g/dL", 12.0, 15.5, []],
    ["PLT", "Platelets", "×10³/µL", 150, 400, [[75, "grade 2 below 75"]]],
])]
# Dose levels of each drug: (name, class, [(start, end, label)], [(hold start, hold end)])
DOSES = BC.get("doses", [])
EVENTS = BC.get("events", [])
COL = {"chemo": "var(--series-2)", "adc": "var(--series-3)", "endo": "var(--series-1)", "targ": "var(--series-6)", "immuno": "var(--series-5)"}
X0 = X1 = None   # set from the case (blood_counts.start / end) or, by default, from the first lab date to just after today


def window(data):
    global X0, X1
    first = min(d for v in data.values() for d in v)
    X0 = date.fromisoformat(BC["start"]) if BC.get("start") else common.month_start(first)
    X1 = date.fromisoformat(BC["end"]) if BC.get("end") else date.fromordinal(common.D(C.today).toordinal() + 20)


def chart(data):
    window(data)
    W, L, R = 1320, 150, 30
    x = lambda s: L + (W - L - R) * ((D(s) if isinstance(s, str) else s) - X0).days / (X1 - X0).days
    s, y = [], 14
    # dose strip
    s.append(f'<text x="{L - 10}" y="{y + 12}" text-anchor="end" font-size="12" font-weight="600" fill="var(--text-primary)">Dose level</text>')
    for i, (name, cls, segs, holds) in enumerate(DOSES):
        by = y + 4 + (i % 2) * 34
        for j, (a, b, lab) in enumerate(segs):
            op = 1 if j == 0 else 0.6 if j == 1 else 0.4
            s.append(f'<rect x="{x(a):.1f}" y="{by}" width="{max(3, x(b) - x(a)):.1f}" height="11" rx="3" fill="{COL[cls]}" opacity="{op}"/>')
        for a, b in holds:
            s.append(f'<rect x="{x(a):.1f}" y="{by}" width="{x(b) - x(a):.1f}" height="11" fill="var(--surface-1)" stroke="{COL[cls]}" stroke-dasharray="3 2"/>')
        cap = " → ".join(f"{common.fmt(a)}: {lab}" if j else lab for j, (a, b, lab) in enumerate(segs) if lab)
        x0 = x(segs[0][0])
        anc, tx = ("end", x(segs[-1][1])) if x0 > W - R - 330 else ("start", x0)
        s.append(f'<text x="{tx:.1f}" y="{by - 3}" text-anchor="{anc}" font-size="11" font-weight="600" fill="var(--text-primary)">{e(name)}</text>'
                 f'<text x="{tx:.1f}" y="{by + 23}" text-anchor="{anc}" font-size="9.5" fill="var(--text-secondary)">{e(cap)}</text>')
    y += 80
    top_all = y
    for key, label, unit, lo, hi, grades in PANELS:
        pts = sorted(data[key].items())
        h = 142
        vmax = max(hi * 1.08, max(v for _, v in pts) * 1.1)
        vmin = 0
        yv = lambda v: y + h - 14 - (v - vmin) / (vmax - vmin) * (h - 26)
        s.append(f'<rect x="{L}" y="{yv(hi):.1f}" width="{W - L - R}" height="{yv(lo) - yv(hi):.1f}" fill="var(--series-1)" opacity="0.08"/>')
        s.append(f'<text x="{L - 10}" y="{y + 20}" text-anchor="end" font-size="12" font-weight="600" fill="var(--text-primary)">{e(label)}</text>'
                 f'<text x="{L - 10}" y="{y + 34}" text-anchor="end" font-size="10" fill="var(--text-secondary)">{e(unit)}</text>'
                 f'<text x="{L - 10}" y="{y + 48}" text-anchor="end" font-size="9.5" fill="var(--text-muted)">normal ≈ {lo:g}–{hi:g}</text>')
        for gv, gl in grades:
            s.append(f'<line x1="{L}" x2="{W - R}" y1="{yv(gv):.1f}" y2="{yv(gv):.1f}" stroke="var(--series-4)" stroke-dasharray="4 3" stroke-width="1"/>'
                     f'<text x="{L + 22}" y="{yv(gv) + (10 if gv < 0.8 else -3):.1f}" font-size="9" fill="var(--text-secondary)">{e(gl)}</text>')
        for v in (lo, hi):
            s.append(f'<text x="{L + 3}" y="{yv(v) - 2:.1f}" font-size="8.5" fill="var(--text-muted)">{v:g}</text>')
        path = "".join(f'{"L" if i else "M"}{x(d):.1f},{yv(v):.1f}' for i, (d, v) in enumerate(pts))
        s.append(f'<path d="{path}" fill="none" stroke="var(--text-primary)" stroke-width="1.6" stroke-linejoin="round"/>')
        for d, v in pts:
            low = v < lo
            s.append(f'<circle cx="{x(d):.1f}" cy="{yv(v):.1f}" r="{3.2 if low else 2.2}" fill="{"var(--series-2)" if low else "var(--text-primary)"}"/>')
        # label each panel's lowest value and the latest one
        for d, v in dict.fromkeys([min(pts, key=lambda p: p[1]), pts[-1]]):
            anc, dx = ("end", -6) if x(d) > W - R - 110 else ("start", 6)
            s.append(f'<text x="{x(d) + dx:.1f}" y="{yv(v) + (12 if v < lo else -6):.1f}" text-anchor="{anc}" font-size="10" font-weight="600" '
                     f'fill="var(--text-primary)" stroke="var(--surface-1)" stroke-width="3" paint-order="stroke">{v:g} ({common.fmt(d)})</text>')
        s.append(f'<line x1="{L}" x2="{W - R}" y1="{y + h - 4}" y2="{y + h - 4}" stroke="var(--grid)"/>')
        y += h
    # year grid and events across all panels
    for yr in range(X0.year + 1, X1.year + 1):
        xx = x(f"{yr}-01-01")
        s.insert(0, f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="10" y2="{y}" stroke="var(--grid)"/>')
        s.append(f'<text x="{xx:.1f}" y="{y + 14}" text-anchor="middle" font-size="11" fill="var(--text-secondary)">{yr}</text>')
    for k, (d, txt) in enumerate(EVENTS):
        xx = x(d)
        s.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{top_all - 6}" y2="{y}" stroke="var(--series-4)" stroke-width="1.2" stroke-dasharray="2 3"/>'
                 f'<text x="{xx - 4:.1f}" y="{y + 28 + k * 13}" text-anchor="end" font-size="10" fill="var(--text-primary)">▲ {e(common.fmt(d))}: {e(txt)}</text>')
    H = y + 30 + 13 * len(EVENTS)
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Blood counts and chemotherapy dose levels">{"".join(s)}</svg>'


def values_table(data):
    ds = sorted(set().union(*[set(v) for v in data.values()]), reverse=True)
    lohi = {k: (lo, hi) for k, _, _, lo, hi, _ in PANELS}

    def cell(k, d):
        v = data[k].get(d)
        if v is None:
            return "<td>–</td>"
        lo, hi = lohi[k]
        return f'<td class="{"low" if v < lo else ""}">{v:g}</td>'
    rows = "".join(f'<tr><td class="n">{common.fmt(d)}</td>{"".join(cell(k, d) for k, *_ in PANELS)}</tr>' for d in ds)
    return (f'<table class="vals"><thead><tr><th>Date</th>{"".join(f"<th>{k}</th>" for k, *_ in PANELS)}</tr></thead>'
            f"<tbody>{rows}</tbody></table>")


CSS = common.CSS + """
@page { size: Letter landscape; margin: 9mm 10mm 10mm; }
body, .viz-root { background: #fff; } .viz-root { padding: 0; font-size: 9pt; } .wrap { max-width: none; }
h1 { font-size: 15pt; margin: 0 0 1mm; } h2 { font-size: 12pt; margin: 0 0 1mm; border: 0; }
.sub { font-size: 8.4pt; color: var(--text-secondary); margin: 0 0 2mm; } .card { padding: 2mm; }
.legend { font-size: 8pt; gap: 1mm 4mm; margin: 0 0 1.5mm; }
section.v + section.v { break-before: page; }
table.vals { font-size: 7.6pt; width: auto; } table.vals td, table.vals th { padding: .5mm 3mm; text-align: right; }
table.vals td.n, table.vals th:first-child { text-align: left; } td.low { color: var(--series-2); font-weight: 700; }
.cols3 { column-count: 3; column-gap: 6mm; } .cols3 table { break-inside: auto; } .note { font-size: 7.6pt; color: var(--text-muted); margin-top: 2mm; }
"""


def main():
    data, used = labs.parse()
    n = len(set().union(*[set(v) for v in data.values()]))
    legend = ('<div class="legend"><span><i class="sw" style="background:var(--series-1);opacity:.25"></i>typical normal range</span>'
              '<span><svg width="10" height="10"><circle cx="5" cy="5" r="3.2" fill="var(--series-2)"/></svg> below normal</span>'
              '<span><svg width="22" height="8"><line x1="0" x2="22" y1="4" y2="4" stroke="var(--series-4)" stroke-dasharray="4 3"/></svg> '
              'severity grade line (common toxicity criteria)</span>'
              '<span><i class="sw" style="background:var(--series-2)"></i>chemotherapy</span><span><i class="sw" style="background:var(--series-3)"></i>antibody–drug conjugate</span>'
              '<span>lighter bar = reduced dose; dashed = held</span></div>')
    body = (f'<section class="v"><h1>{e(BC["title"])}</h1>'
            f'<p class="sub">{C.text("blood_counts_sub", used=used, n=n)}</p>'
            f'{legend}<div class="card">{chart(data)}</div></section>'
            f'<section class="v"><h2>All values</h2><p class="sub">Newest first. WBC = white blood cells, ANC = neutrophils (both ×10³/µL); '
            f'HGB = hemoglobin (g/dL); PLT = platelets (×10³/µL). Orange bold = below the typical normal range. "–" = not in a complete table row.</p>'
            f'<div class="cols3">{values_table(data)}</div>'
            f'</section>')
    doc = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Blood counts</title><style>{CSS}</style></head>'
           f'<body><div class="viz-root"><div class="wrap">{body}</div></div></body></html>')
    pdf = common.write_and_print("blood_counts", doc, f"blood_counts_{C.built}.pdf")
    print("built:", pdf.name, pdf.stat().st_size, "bytes")
    return pdf
