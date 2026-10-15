"""Weight, Karnofsky / Palliative Performance Scale and pain score over time, under the treatment eras.
From the vitals lines in the published notes; axis ranges and the page's narrative come from the case file (``vitals:``)."""
import html
import math
import re
from datetime import date

from . import common, labs, timeline

e = html.escape
D = common.D
C = common.case()
V = C.get("vitals", {})
X0 = date.fromisoformat(V["start"]) if V.get("start") else date(2000, 1, 1)   # default narrowed to the first measurement in parse()
X1 = date.fromisoformat(V["end"]) if V.get("end") else common.year_end(C.today)
WEIGHT = [re.compile(r"Weight: (\d{2,3}(?:\.\d+)?) ?lb\b"), re.compile(r"Weight: \d+(?:\.\d+)? kg \((\d{2,3}(?:\.\d+)?) lb\)")]
PAIN = re.compile(r"Pain Scale: (\d{1,2})\b")
KPS = re.compile(r"Karnofsky:? (\d{2,3})(?:-(\d{2,3}))?%")
PPS = re.compile(r"Palliative Performance Scale\s*\n\s*(\d{2,3})%")
# A weight the patient reports in the narrative (telemedicine visits have no vitals line), e.g. "weight today is approximately 145-147 lb"
REPORTED = re.compile(r"[Ww]eight[^.\n]{0,40}?(\d{2,3})\s*-\s*(\d{2,3}) ?lb")
ERAS = []   # treatment eras on the axis, set in parse()
ERA_COL = {"endo": "var(--series-1)", "chemo": "var(--series-2)", "adc": "var(--series-3)", "targ": "var(--series-6)", "immuno": "var(--series-5)"}


def weight_axis(w):
    """(min, max, ticks) for the weight panel: from the case, else rounded around the data."""
    if V.get("weight_axis"):
        lo, hi, ticks = V["weight_axis"]
        return lo, hi, ticks
    lo = math.floor(min(v for _, v in w) / 10) * 10 - 5
    hi = math.ceil(max(v for _, v in w) / 10) * 10 + 5
    return lo, hi, list(range(lo + 5, hi + 1, 10))


def parse():
    """{measure: {iso date: value}}; Karnofsky ranges ("70-80%") are kept as (low, high)."""
    global X0, ERAS
    out = {"weight": {}, "pain": {}, "kps": {}, "pps": {}, "reported": {}}
    src = {}
    for f in sorted(labs.notes().glob("2*.md")):
        d = f.name[:10]
        if d < X0.isoformat():
            continue
        text = f.read_text(encoding="utf-8")
        for rx in WEIGHT:
            m = rx.search(text)
            if m and 80 <= float(m.group(1)) <= 250:
                out["weight"].setdefault(d, float(m.group(1)))
                src.setdefault(d, f.name.split("_")[1])
                break
        m = REPORTED.search(text)
        if m and d not in out["weight"]:
            out["reported"][d] = (int(m.group(1)), int(m.group(2)))
            src.setdefault(d, f.name.split("_")[1])
        m = PPS.search(text)
        if m:
            out["pps"][d] = int(m.group(1))
            src.setdefault(d, f.name.split("_")[1])
        m = PAIN.search(text)
        if m:
            out["pain"].setdefault(d, int(m.group(1)))
        m = KPS.search(text)
        if m:
            lo = int(m.group(1)); hi = int(m.group(2) or lo)
            out["kps"].setdefault(d, (lo, hi))
    if not V.get("start") and out["weight"]:
        X0 = common.month_start(min(out["weight"]))
    ERAS = [(b["label"], b["cls"], b["start"], b["end"]) for b in timeline.systemic() if b["end"] >= X0.isoformat()]
    return out, src


def chart(data):
    W, L, R = 1320, 170, 30
    x = lambda s: L + (W - L - R) * max(0, ((D(s) if isinstance(s, str) else s) - X0).days) / (X1 - X0).days
    s, y = [], 10
    # treatment eras
    s.append(f'<text x="{L - 10}" y="{y + 12}" text-anchor="end" font-size="12" font-weight="600" fill="var(--text-primary)">Treatment</text>')
    for i, (name, cls, a, b) in enumerate(ERAS):
        x0, x1 = x(a), x(b)
        by = y + 2 + (i % 2) * 22
        s.append(f'<rect x="{x0:.1f}" y="{by}" width="{max(3, x1 - x0):.1f}" height="9" rx="3" fill="{ERA_COL[cls]}"/>'
                 f'<text x="{x0:.1f}" y="{by + 19}" font-size="9.5" fill="var(--text-secondary)">{e(name)}</text>')
    y += 52
    top = y

    def panel(title, unit, pts, h, vmin, vmax, ticks, fmt_v, band=None, step=False, bars=False):
        nonlocal y
        yv = lambda v: y + h - 12 - (v - vmin) / (vmax - vmin) * (h - 24)
        s.append(f'<text x="{L - 10}" y="{y + 20}" text-anchor="end" font-size="12" font-weight="600" fill="var(--text-primary)">{e(title)}</text>'
                 f'<text x="{L - 10}" y="{y + 34}" text-anchor="end" font-size="10" fill="var(--text-secondary)">{e(unit)}</text>')
        for t in ticks:
            s.append(f'<line x1="{L}" x2="{W - R}" y1="{yv(t):.1f}" y2="{yv(t):.1f}" stroke="var(--grid)" stroke-width="0.6"/>'
                     f'<text x="{L + 3}" y="{yv(t) - 2:.1f}" font-size="8.5" fill="var(--text-muted)">{t:g}</text>')
        if bars:
            for d, v in pts:
                s.append(f'<rect x="{x(d) - 3:.1f}" y="{yv(v):.1f}" width="6" height="{max(1.5, yv(vmin) - yv(v)):.1f}" rx="1.5" '
                         f'fill="{"var(--series-2)" if v >= 4 else "var(--series-5)"}"/>')
        elif band:   # Karnofsky ranges: shaded from low to high, line through the middle
            path = "".join(f'{"L" if i else "M"}{x(d):.1f},{yv((lo + hi) / 2):.1f}' for i, (d, (lo, hi)) in enumerate(pts))
            for d, (lo, hi) in pts:
                if hi > lo:
                    s.append(f'<rect x="{x(d) - 3:.1f}" y="{yv(hi):.1f}" width="6" height="{yv(lo) - yv(hi):.1f}" rx="2" fill="var(--series-1)" opacity="0.35"/>')
            s.append(f'<path d="{path}" fill="none" stroke="var(--text-primary)" stroke-width="1.6"/>')
            for d, (lo, hi) in pts:
                s.append(f'<circle cx="{x(d):.1f}" cy="{yv((lo + hi) / 2):.1f}" r="2.4" fill="var(--text-primary)"/>')
        else:
            path = "".join(f'{"L" if i else "M"}{x(d):.1f},{yv(v):.1f}' for i, (d, v) in enumerate(pts))
            s.append(f'<path d="{path}" fill="none" stroke="var(--text-primary)" stroke-width="1.7" stroke-linejoin="round"/>')
            for d, v in pts:
                s.append(f'<circle cx="{x(d):.1f}" cy="{yv(v):.1f}" r="2.4" fill="var(--text-primary)"/>')
        return yv

    w = sorted(data["weight"].items())
    wlo, whi, wticks = weight_axis(w)
    yv = panel("Weight", "lb", w, 300, wlo, whi, wticks, "{:g}")
    hi_p, lo_p = max(w, key=lambda p: p[1]), min(w, key=lambda p: p[1])
    for d, v in dict.fromkeys([w[0], hi_p, lo_p, w[-1]]):
        anc, dx = ("end", -6) if x(d) > W - R - 120 else ("start", 6)
        s.append(f'<text x="{x(d) + dx:.1f}" y="{yv(v) - 6:.1f}" text-anchor="{anc}" font-size="10" font-weight="600" fill="var(--text-primary)" '
                 f'stroke="var(--surface-1)" stroke-width="3" paint-order="stroke">{v:g} lb ({common.fmt(d)})</text>')
    for d, (lo, hi) in sorted(data["reported"].items()):
        mid = (lo + hi) / 2
        prev = max((p for p in w if p[0] < d), default=None)
        if prev:
            s.append(f'<line x1="{x(prev[0]):.1f}" y1="{yv(prev[1]):.1f}" x2="{x(d):.1f}" y2="{yv(mid):.1f}" stroke="var(--text-primary)" '
                     f'stroke-width="1.3" stroke-dasharray="3 3"/>')
        s.append(f'<line x1="{x(d):.1f}" x2="{x(d):.1f}" y1="{yv(hi):.1f}" y2="{yv(lo):.1f}" stroke="var(--text-primary)" stroke-width="1.5"/>'
                 f'<circle cx="{x(d):.1f}" cy="{yv(mid):.1f}" r="3.6" fill="var(--surface-1)" stroke="var(--text-primary)" stroke-width="1.6"/>'
                 f'<text x="{x(d) - 4:.1f}" y="{yv(lo) + 15:.1f}" text-anchor="end" font-size="10" font-weight="600" fill="var(--text-primary)" '
                 f'stroke="var(--surface-1)" stroke-width="3" paint-order="stroke">{lo}–{hi} lb reported ({common.fmt(d)})</text>')
    y += 300
    s.append(f'<line x1="{L}" x2="{W - R}" y1="{y - 4}" y2="{y - 4}" stroke="var(--grid)"/>')
    k = sorted(data["kps"].items())
    yv = panel("Performance status", "Karnofsky / PPS %", k, 210, 40, 100, [50, 60, 70, 80, 90, 100], "{:g}", band=True)
    for d, v in sorted(data["pps"].items()):
        xx, yy = x(d), yv(v)
        s.append(f'<path d="M{xx:.1f},{yy - 6:.1f} L{xx + 6:.1f},{yy:.1f} L{xx:.1f},{yy + 6:.1f} L{xx - 6:.1f},{yy:.1f} Z" fill="var(--series-2)" '
                 f'stroke="var(--surface-1)" stroke-width="1.5"/>')
    s.append(f'<text x="{W - R - 4}" y="{yv(100) + 10:.1f}" text-anchor="end" font-size="9" fill="var(--text-muted)">100 = normal activity · '
             f'70 = cares for self, unable to work · 50 = needs considerable help</text>'
             f'<circle cx="{L + 70}" cy="{yv(52):.1f}" r="2.6" fill="var(--text-primary)"/>'
             f'<text x="{L + 78}" y="{yv(52) + 3.5:.1f}" font-size="9.5" fill="var(--text-secondary)">Karnofsky (oncology visits)</text>'
             f'<path d="M{L + 250},{yv(52) - 5:.1f} l5,5 l-5,5 l-5,-5 z" fill="var(--series-2)"/>'
             f'<text x="{L + 260}" y="{yv(52) + 3.5:.1f}" font-size="9.5" fill="var(--text-secondary)">Palliative Performance Scale (palliative visits)</text>')
    y += 210
    s.append(f'<line x1="{L}" x2="{W - R}" y1="{y - 4}" y2="{y - 4}" stroke="var(--grid)"/>')
    p = sorted(data["pain"].items())
    panel("Pain score", "0–10 at the visit", p, 140, 0, 10, [0, 5, 10], "{:g}", bars=True)
    y += 140
    for yr in range(X0.year + 1, X1.year + 1):
        xx = x(f"{yr}-01-01")
        s.insert(0, f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="8" y2="{y}" stroke="var(--grid)"/>')
        s.append(f'<text x="{xx:.1f}" y="{y + 14}" text-anchor="middle" font-size="11" fill="var(--text-secondary)">{yr}</text>')
    return f'<svg viewBox="0 0 {W} {y + 22}" width="100%" role="img" aria-label="Weight, performance status and pain over time">{"".join(s)}</svg>'


def table(data, src):
    ds = sorted(set(data["weight"]) | set(data["kps"]) | set(data["pain"]) | set(data["pps"]) | set(data["reported"]), reverse=True)
    wt = lambda d: (f"{data['weight'][d]:g}" if d in data["weight"]
                    else f"{data['reported'][d][0]}–{data['reported'][d][1]} (reported)" if d in data["reported"] else "–")
    kp = lambda d: (f"{data['kps'][d][0]}–{data['kps'][d][1]}%" if data["kps"][d][0] != data["kps"][d][1] else f"{data['kps'][d][0]}%") if d in data["kps"] else "–"
    rows = "".join(f'<tr><td class="n">{common.fmt(d)}</td><td>{wt(d)}</td><td>{kp(d)}</td><td>{f"{data['pps'][d]}%" if d in data["pps"] else "–"}</td><td>{data["pain"].get(d, "–")}</td>'
                   f'<td class="muted">{e(src.get(d, ""))}</td></tr>' for d in ds)
    return ('<table class="vals"><thead><tr><th>Date</th><th>Weight (lb)</th><th>Karnofsky</th><th>PPS</th><th>Pain</th><th>Note</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>')


CSS = common.CSS + """
@page { size: Letter landscape; margin: 9mm 10mm 10mm; }
body, .viz-root { background: #fff; } .viz-root { padding: 0; font-size: 9pt; } .wrap { max-width: none; }
h1 { font-size: 15pt; margin: 0 0 1mm; } h2 { font-size: 12pt; margin: 0 0 1mm; border: 0; }
.sub { font-size: 8.4pt; color: var(--text-secondary); margin: 0 0 2mm; } .card { padding: 2mm; } .muted { color: var(--text-secondary); }
.card svg { max-height: 150mm; width: auto; max-width: 100%; display: block; margin: 0 auto; }
section.v + section.v { break-before: page; }
.cols3 { column-count: 3; column-gap: 6mm; } table.vals { font-size: 7.6pt; } table.vals td, table.vals th { padding: .5mm 2mm; }
.note { font-size: 7.6pt; color: var(--text-muted); margin-top: 2mm; }
"""


def main():
    data, src = parse()
    w = sorted(data["weight"].items())
    peak = max(w, key=lambda p: p[1])
    change = (w[-1][1] - peak[1]) / peak[1] * 100
    rep = "; ".join(f"{lo}–{hi} lb" for d, (lo, hi) in sorted(data["reported"].items())) or "no weight"
    stats = (f'{len(data["weight"])} measured weights, {len(data["kps"])} Karnofsky scores, {len(data["pps"])} Palliative Performance Scale scores, '
             f'{len(data["pain"])} pain scores. Weight rose from {w[0][1]:g} lb ({common.fmt(w[0][0])}) to a peak of {peak[1]:g} lb '
             f'({common.fmt(peak[0])}), then fell to {w[-1][1]:g} lb ({common.fmt(w[-1][0])}; {change:+.0f}% from the peak).')
    body = (f'<section class="v"><h1>{e(V["title"])}</h1>'
            f'<p class="sub">{C.text("vitals_sub", stats=stats, reported=rep, n_pps=len(data["pps"]))}</p><div class="card">{chart(data)}</div></section>'
            f'<section class="v"><h2>All values</h2><p class="sub">Newest first. "–" = not recorded at that visit.</p><div class="cols3">{table(data, src)}</div>'
            f'</section>')
    doc = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Weight, function and pain</title><style>{CSS}</style></head>'
           f'<body><div class="viz-root"><div class="wrap">{body}</div></div></body></html>')
    pdf = common.write_and_print("vitals", doc, f"weight_function_pain_{C.built}.pdf")
    print("built:", pdf.name, pdf.stat().st_size, "bytes;", {k: len(v) for k, v in data.items()})
    return pdf
