"""Three views of the disease course for print: where the disease has been (body map), how each treatment line worked
(swimmer chart and scorecard), and hospital / ED use by year. Data come from the case file (``overview:``) and the events."""
import html
from collections import defaultdict
from datetime import timedelta

from . import common, timeline

e = html.escape
D = common.D
C = common.case()
O = C.get("overview", {})

# Sites: {n, site, group, x, y (figure coordinates, viewer's left = patient's right), first, how, course, status, [bar: [x, y1, y2]]}
SITES = O.get("sites", [])
STATUS = {"removed": ("Removed surgically", "var(--text-muted)"), "treated": ("Treated / stable or improved", "var(--series-1)"),
          "active": ("Active / new", "var(--series-2)")}
NEGATIVE = O.get("negative", "")


def body_svg():
    ink = "var(--text-secondary)"
    fig = (f'<g fill="none" stroke="{ink}" stroke-width="1.6" stroke-linejoin="round">'
           '<circle cx="150" cy="52" r="30"/>'
           '<path d="M138,80 L138,96 L162,96 L162,80"/>'
           '<path d="M96,104 Q150,92 204,104 L214,190 Q210,260 200,300 L206,340 Q150,356 94,340 L100,300 Q90,260 86,190 Z"/>'
           '<path d="M96,104 Q76,112 70,140 L56,250 L48,330 L62,334 L74,254 L92,160"/>'
           '<path d="M204,104 Q224,112 230,140 L244,250 L252,330 L238,334 L226,254 L208,160"/>'
           '<path d="M98,340 L104,470 L100,600 L128,600 L130,470 L146,352"/>'
           '<path d="M202,340 L196,470 L200,600 L172,600 L170,470 L154,352"/>'
           '</g><line x1="150" y1="200" x2="150" y2="310" stroke="var(--grid)" stroke-width="4" stroke-linecap="round"/>'
           f'<text x="30" y="20" font-size="10" fill="{ink}">{e(O.get("right_label", "patient's right"))}</text>'
           f'<text x="270" y="20" text-anchor="end" font-size="10" fill="{ink}">{e(O.get("left_label", "patient's left"))}</text>')
    marks = []
    for st_ in SITES:
        n, x, y, st = st_["n"], st_["x"], st_["y"], st_["status"]
        col = STATUS[st][1]
        if st_.get("bar"):   # e.g. the spine: a bar, numbered at its top
            bx, y1, y2 = st_["bar"]
            marks.append(f'<line x1="{bx}" y1="{y1}" x2="{bx}" y2="{y2}" stroke="{col}" stroke-width="7" stroke-linecap="round" opacity="0.85"/>')
            marks.append(f'<circle cx="{x}" cy="{y}" r="9" fill="var(--surface-1)" stroke="{col}" stroke-width="2"/>'
                         f'<text x="{x}" y="{y + 3.5}" text-anchor="middle" font-size="9.5" font-weight="700" fill="var(--text-primary)">{n}</text>')
            continue
        fill = col if st != "removed" else "var(--surface-1)"
        txt = "#fff" if st != "removed" else "var(--text-primary)"
        marks.append(f'<circle cx="{x}" cy="{y}" r="9" fill="{fill}" stroke="{col}" stroke-width="2"/>'
                     f'<text x="{x}" y="{y + 3.5}" text-anchor="middle" font-size="9.5" font-weight="700" fill="{txt}">{n}</text>')
    return f'<svg viewBox="20 0 260 610" width="100%" role="img" aria-label="Body outline with numbered sites of disease">{fig}{"".join(marks)}</svg>'


def sites_table():
    rows, last = [], None
    for st_ in SITES:
        n, site, grp, first, how, course, st = (st_[k] for k in ("n", "site", "group", "first", "how", "course", "status"))
        if grp != last:
            rows.append(f'<tr class="grp"><td colspan="5">{e(grp)}</td></tr>')
            last = grp
        rows.append(f'<tr><td class="num"><i class="dot" style="background:{STATUS[st][1] if st != "removed" else "#fff"};border-color:{STATUS[st][1]}"></i>{n}</td>'
                    f'<td><b>{e(site)}</b></td><td class="n">{e(first)}<br><span class="muted">{e(how)}</span></td><td>{e(course)}</td>'
                    f'<td class="n">{e(STATUS[st][0])}</td></tr>')
    return (f'<table class="sites"><thead><tr><th>#</th><th>Site</th><th>First found</th><th>Treatment and course</th><th>Now</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


# --- B. how each metastatic line worked ------------------------------------------------------------------------------
LINES = [tuple(x) for x in O.get("lines", [])]  # (line, label, class, start, end, ongoing, best (date, text) or None, why ended, prog | tox | now)
CLS = {"endo": "var(--series-1)", "targ": "var(--series-6)", "chemo": "var(--series-2)", "adc": "var(--series-3)"}


def ca_stats(start, end):
    vals = [(d, v) for d, v in C.marker if D(start) - timedelta(days=60) <= D(d) <= D(end) + timedelta(days=21)]
    if not vals:
        return None
    near = [p for p in vals if abs((D(p[0]) - D(start)).days) <= 60]
    first = min(near, key=lambda p: abs((D(p[0]) - D(start)).days)) if near else None
    during = [p for p in vals if D(start) <= D(p[0]) <= D(end) + timedelta(days=21)] or vals
    low = min(during, key=lambda p: p[1])
    last = max(during, key=lambda p: p[0])
    return first, low, last


def months(a, b):
    return (D(b) - D(a)).days / 30.44


def swimmer_svg():
    W, L = 1320, 250
    maxm = max(months(s, t) for _, _, _, s, t, *_ in LINES)
    scale = (W - L - 330) / maxm
    s, y = [], 26
    for m in range(0, int(maxm) + 7, 6):
        x = L + m * scale
        s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="18" y2="{18 + 50 * len(LINES)}" stroke="var(--grid)"/>'
                 f'<text x="{x:.1f}" y="{26 + 50 * len(LINES)}" text-anchor="middle" font-size="10.5" fill="var(--text-secondary)">{m}</text>')
    s.append(f'<text x="{L + maxm * scale / 2:.1f}" y="{42 + 50 * len(LINES)}" text-anchor="middle" font-size="10.5" fill="var(--text-secondary)">months on treatment</text>')
    for ln, name, cls, a, b, ongoing, best, why, kind in LINES:
        dur = months(a, b)
        x1 = L + dur * scale
        s.append(f'<text x="{L - 12}" y="{y + 11}" text-anchor="end" font-size="12.5" font-weight="700" fill="var(--text-primary)">{ln} {e(name)}</text>'
                 f'<text x="{L - 12}" y="{y + 25}" text-anchor="end" font-size="10" fill="var(--text-secondary)">{common.fmt(a)} – {"now" if ongoing else common.fmt(b)}</text>'
                 f'<rect x="{L}" y="{y}" width="{max(3, x1 - L):.1f}" height="16" rx="4" fill="{CLS[cls]}"/>')
        if best:
            bx = L + months(a, best[0]) * scale
            s.append(f'<path d="M{bx - 6:.1f},{y - 5} L{bx + 6:.1f},{y - 5} L{bx:.1f},{y + 5} Z" fill="var(--surface-1)" stroke="var(--text-primary)" stroke-width="1.5"/>')
        end = {"prog": f'<path d="M{x1 + 4:.1f},{y + 14} L{x1 + 16:.1f},{y + 14} L{x1 + 10:.1f},{y + 2} Z" fill="var(--text-primary)"/>',
               "tox": f'<text x="{x1 + 10:.1f}" y="{y + 14}" text-anchor="middle" font-size="15" font-weight="700" fill="var(--series-2)">✕</text>',
               "now": f'<path d="M{x1 + 3:.1f},{y} l10,8 l-10,8 z" fill="{CLS[cls]}"/>'}[kind]
        s.append(end + f'<text x="{x1 + 22:.1f}" y="{y + 9}" font-size="10.5" fill="var(--text-primary)">{dur:.0f} mo · {e(why)}</text>')
        st = ca_stats(a, b)
        if st:
            f_, lo, la = st
            s.append(f'<text x="{x1 + 22:.1f}" y="{y + 23}" font-size="9.5" fill="var(--text-secondary)">{timeline.mname()} {f"{f_[1]:g}" if f_ else "–"} → lowest {lo[1]:g} → {la[1]:g}</text>')
        y += 50
    H = 50 + 50 * len(LINES)
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Duration and outcome of each treatment line">{"".join(s)}</svg>'


def score_table():
    rows = []
    for ln, name, cls, a, b, ongoing, best, why, kind in LINES:
        st = ca_stats(a, b)
        ca = ((f"{st[0][1]:g} ({common.fmt(st[0][0])})" if st[0] else O.get("no_start_value", "no value at start"))
              + f" → lowest {st[1][1]:g} ({common.fmt(st[1][0])}) → {st[2][1]:g} ({common.fmt(st[2][0])})" if st else "no values")
        rows.append(f'<tr><td class="num">{ln}</td><td><b>{e(name)}</b></td><td class="n">{common.fmt(a)} – {"ongoing" if ongoing else common.fmt(b)}'
                    f'<br><span class="muted">{months(a, b):.0f} months</span></td>'
                    f'<td>{e(best[1] + " · " + common.fmt(best[0])) if best else "not imaged / not yet"}</td><td>{e(ca)}</td><td>{e(why)}</td></tr>')
    return ('<table class="score"><thead><tr><th></th><th>Treatment</th><th>Dates</th><th>Best response on imaging</th>'
            f'<th>{timeline.mname()} at start → lowest → at stop ({C["tumor_marker"]["unit"]}; normal ≤ {timeline.uln()})</th><th>Why it ended</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')


# --- C. hospital and ED use per year ---------------------------------------------------------------------------------
def usage():
    per = defaultdict(lambda: defaultdict(float))
    for x in timeline.events():
        if x["kind"] == "img":
            continue
        yr = int(x["date"][:4])
        if x["kind"] == "ed":
            per[yr]["ED visits"] += 1
        if x["kind"] in ("surgery", "proc"):
            per[yr]["Operations and procedures"] += 1
        if x["kind"] == "reduction":
            per[yr]["Closed reductions"] += 1
        if x.get("stay"):
            nights = (D(x["stay"][1]) - D(x["stay"][0])).days
            if nights >= 1:
                per[yr]["Hospital admissions"] += 1
                per[yr]["Nights in hospital"] += nights
    for yr, k, v in O.get("usage_adjust", []):
        per[yr][k] += v
    return per


METRICS = ["ED visits", "Hospital admissions", "Nights in hospital", "Operations and procedures"]


def usage_svg(per):
    # default: from the first hospital/ED event's year to the current year
    first = min([x["date"][:4] for x in C.get("events", []) if x["kind"] != "img"] or [C.today[:4]])
    y0, y1 = O.get("usage_years", [int(first), int(C.today[:4])])
    years = list(range(y0, y1 + 1))
    W, pw, gap = 1320, 300, 26
    s = []
    for i, m in enumerate(METRICS):
        x0 = 20 + i * (pw + gap)
        vals = [per[y][m] for y in years]
        vmax = max(vals + [1])
        s.append(f'<text x="{x0}" y="18" font-size="13" font-weight="700" fill="var(--text-primary)">{e(m)}</text>')
        bw = (pw - 20) / len(years)
        for j, (y, v) in enumerate(zip(years, vals)):
            h = 150 * v / vmax
            bx = x0 + j * bw + 4
            s.append(f'<rect x="{bx:.1f}" y="{200 - h:.1f}" width="{bw - 10:.1f}" height="{max(h, 1):.1f}" rx="4" fill="var(--series-1)"/>'
                     f'<text x="{bx + (bw - 10) / 2:.1f}" y="{194 - h:.1f}" text-anchor="middle" font-size="11.5" font-weight="600" fill="var(--text-primary)">{v:g}</text>'
                     f'<text x="{bx + (bw - 10) / 2:.1f}" y="216" text-anchor="middle" font-size="11" fill="var(--text-secondary)">{y}</text>')
        s.append(f'<line x1="{x0}" x2="{x0 + pw - 16}" y1="200" y2="200" stroke="var(--text-muted)"/>')
    return f'<svg viewBox="0 0 {W} 226" width="100%" role="img" aria-label="Hospital and ED use per year">{"".join(s)}</svg>'


def usage_table():
    rows = []
    for x in sorted(C.get("events", []), key=lambda x: x["date"]):
        stay = ""
        if x.get("stay"):
            n = (D(x["stay"][1]) - D(x["stay"][0])).days
            stay = f"{common.fmt(x['stay'][0])} – {common.fmt(x['stay'][1])} ({n} night{'s' if n != 1 else ''})" if n else "same day"
        rows.append(f'<tr><td class="n">{common.fmt(x["date"])}</td><td class="n">{e(timeline.KIND[x["kind"]][1])}</td><td>{e(x["text"])}</td><td class="n">{e(stay)}</td></tr>')
    return f'<table class="use"><thead><tr><th>Date</th><th>Kind</th><th>Event</th><th>Stay</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'


CSS = common.CSS + """
@page { size: Letter landscape; margin: 9mm 10mm 10mm; }
body, .viz-root { background: #fff; } .viz-root { padding: 0; font-size: 9pt; } .wrap { max-width: none; }
section.v + section.v { break-before: page; }
h1 { font-size: 15pt; margin: 0 0 1mm; } h2 { font-size: 12.5pt; margin: 0 0 1mm; border: 0; }
.sub { font-size: 8.4pt; color: var(--text-secondary); margin: 0 0 2mm; } .muted { color: var(--text-secondary); }
.map { display: grid; grid-template-columns: 62mm 1fr; gap: 5mm; align-items: start; }
table { font-size: 7.9pt; } th, td { padding: .7mm 1.4mm; vertical-align: top; } td.num { font-weight: 700; white-space: nowrap; }
tr.grp td { background: #f1f0ec; font-weight: 700; font-size: 8pt; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; border: 2px solid; margin-right: 4px; vertical-align: -1px; }
.legend { font-size: 8pt; gap: 1mm 4mm; margin: 1mm 0 2mm; } .legend svg { vertical-align: -2px; margin-right: 3px; }
.card { padding: 2mm; } table.score { margin-top: 2mm; font-size: 8.2pt; } table.use { margin-top: 1.5mm; font-size: 7.5pt; } table.use td, table.use th { padding: .45mm 1.4mm; }
.note { font-size: 7.6pt; color: var(--text-muted); margin-top: 2mm; }
"""


def main():
    per = usage()
    status_legend = "".join(f'<span><i class="dot" style="background:{c if k != "removed" else "#fff"};border-color:{c}"></i>{e(n)}</span>'
                            for k, (n, c) in STATUS.items())
    swim_legend = ('<span><svg width="12" height="12"><path d="M1,2 L11,2 L6,10 Z" fill="#fff" stroke="currentColor" stroke-width="1.4"/></svg>best response on imaging</span>'
                   '<span><svg width="12" height="12"><path d="M1,11 L11,11 L6,1 Z" fill="currentColor"/></svg>stopped: progression</span>'
                   '<span style="color:var(--series-2)"><b>✕</b></span><span>stopped: side effects</span>'
                   '<span>▶ ongoing</span>'
                   + "".join(f'<span><i class="sw" style="background:{c}"></i>{n}</span>' for n, c in
                             [("Endocrine", CLS["endo"]), ("Targeted", CLS["targ"]), ("Chemotherapy", CLS["chemo"]), ("Antibody–drug conjugate", CLS["adc"])]))
    body = (f'<section class="v"><h1>Disease course overview</h1>'
            f'<p class="sub">{C.summary} · prepared {C.built} from the de-identified records.</p>'
            f'<h2>A. Where the disease has been</h2><p class="sub">{C.text("overview_sites")} '
            f'{e(NEGATIVE)}</p><div class="legend">{status_legend}</div>'
            f'<div class="map"><div class="card">{body_svg()}</div><div>{sites_table()}</div></div></section>'
            f'<section class="v"><h2>{e(O["lines_title"])}</h2>'
            f'<p class="sub">{C.text("overview_lines", marker=timeline.mname())}</p><div class="legend">{swim_legend}</div><div class="card">{swimmer_svg()}</div>{score_table()}</section>'
            f'<section class="v"><h2>{e(O["usage_title"])}</h2>'
            f'<p class="sub">{C.text("overview_usage")}</p>'
            f'<div class="card">{usage_svg(per)}</div>{usage_table()}'
            f'</section>')
    doc = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Disease course overview</title><style>{CSS}</style></head>'
           f'<body><div class="viz-root"><div class="wrap">{body}</div></div></body></html>')
    pdf = common.write_and_print("disease_overview", doc, f"disease_overview_{C.built}.pdf")
    print("built:", pdf.name, pdf.stat().st_size, "bytes")
    return pdf
