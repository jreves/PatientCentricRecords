"""Pathology and tumour-genetics results alongside treatment: a tracks view (one row per marker) and a mirrored timeline
(findings above the axis, treatments below, the tumour marker along the bottom). Data come from the case file
(``pathology:``): tests and their results, progressions without new testing, the markers to show, the treatments with the
finding each rested on, and the broken time axis."""
import html
from datetime import date

from . import common, timeline

e = html.escape
D = common.D
C = common.case()
P = C.get("pathology", {})

# status: pos (positive / mutation found) | neg (negative / not found) | disc (records disagree) | vus (uncertain significance)
TESTS = P.get("tests", [])
UNTESTED = [tuple(x) for x in P.get("untested", [])]
MARKERS = [tuple(x) for x in P.get("markers", [])]
SHORT = P.get("short", {})
STATUS = {"pos": ("Positive / mutation found", "var(--text-primary)"), "neg": ("Negative / not found", "var(--text-muted)"),
          "disc": ("Records disagree", "var(--series-4)"), "vus": ("Uncertain significance (VUS)", "var(--series-5)")}
# (name, class, start, end, basis, test id it rested on or None)
TREAT = [tuple(x) for x in P.get("treatments", [])]
CLS = {k: tuple(v) for k, v in P.get("classes", {"endo": ["Endocrine", "var(--series-1)"], "targ": ["Targeted", "var(--series-6)"],
                                                 "chemo": ["Chemotherapy", "var(--series-2)"], "adc": ["Antibody–drug conjugate", "var(--series-3)"]}).items()}
LINK = set(P.get("link_classes", ["targ"]))   # treatment classes drawn with a link to the test they rested on
# The time axis: one segment, or two with the gap between them compressed (e.g. years with no tests or treatment changes).
# Default: one segment from January of the first test's year to the end of the current year, ticked every two years.
_first = min([t["date"] for t in TESTS] + [x[2] for x in TREAT] or [C.today])
SEGMENTS = [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in P.get("axis", [[f"{_first[:4]}-01-01", common.year_end(C.today).isoformat()]])]
TICKS = P.get("ticks", [list(range(int(_first[:4]) + 1, common.year_end(C.today).year + 1, 2))])


# --- a broken time axis: 2006–2011 compressed, 2016–2026 wide ----------------------------------------------------
class Axis:
    """A broken time axis: the first segment compressed (``early_share`` of the width), a small gap, then the rest."""
    def __init__(self, x0, x1, gap=22, early_share=0.2):
        if len(SEGMENTS) == 1:
            (a0, a1), = SEGMENTS
            self.segs, self.gap = [(a0, a1, x0, x1)], None
            return
        w = x1 - x0 - gap
        (a0, a1), (b0, b1) = SEGMENTS
        a = (a0, a1, x0, x0 + w * early_share)
        b = (b0, b1, x0 + w * early_share + gap, x1)
        self.segs = [a, b]
        self.gap = (a[3], b[2])

    def x(self, s):
        d = D(s) if isinstance(s, str) else s
        for d0, d1, p0, p1 in self.segs:
            if d <= d1 or (d0, d1, p0, p1) == self.segs[-1]:
                d = max(d, d0)
                return p0 + (p1 - p0) * (d - d0).days / (d1 - d0).days
        return self.segs[-1][3]

    def ticks(self):
        return [(y, self.x(f"{y}-01-01")) for y in sum(TICKS, [])]

    def svg_grid(self, y0, y1, label_y):
        s = []
        for yr, x in self.ticks():
            s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y0}" y2="{y1}" stroke="var(--grid)"/>'
                     f'<text x="{x:.1f}" y="{label_y}" text-anchor="middle" font-size="11" fill="var(--text-secondary)">{yr}</text>')
        if self.gap:
            g0, g1 = self.gap
            s.append(f'<rect x="{g0 + 3:.1f}" y="{y0}" width="{g1 - g0 - 6:.1f}" height="{y1 - y0}" fill="var(--surface-2, #f3f2ee)"/>'
                     f'<text x="{(g0 + g1) / 2:.1f}" y="{label_y}" text-anchor="middle" font-size="10" fill="var(--text-muted)">⋯</text>')
        return "".join(s)


def glyph(kind, x, y, r=7, fill="var(--text-primary)"):
    if kind == "tissue":
        return f'<rect x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r}" height="{2 * r}" rx="2" fill="{fill}"/>'
    if kind == "blood":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}"/>'
    return f'<path d="M{x:.1f},{y - r - 1:.1f} L{x + r + 1:.1f},{y:.1f} L{x:.1f},{y + r + 1:.1f} L{x - r - 1:.1f},{y:.1f} Z" fill="{fill}"/>'


def status_mark(st, x, y, r=6.5):
    col = STATUS[st][1]
    if st == "neg":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="var(--surface-1)" stroke="{col}" stroke-width="2"/>'
    if st == "disc":
        return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="var(--surface-1)" stroke="{col}" stroke-width="2"/>'
                f'<path d="M{x:.1f},{y - r:.1f} A{r},{r} 0 0 1 {x:.1f},{y + r:.1f} Z" fill="{col}"/>')
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{col}"/>'


LEGEND = ('<div class="legend">'
          '<span><svg width="14" height="14">' + glyph("tissue", 7, 7, 5) + '</svg>tissue pathology</span>'
          '<span><svg width="14" height="14">' + glyph("blood", 7, 7, 5) + '</svg>blood test of tumour DNA (liquid biopsy)</span>'
          '<span><svg width="16" height="16">' + glyph("germline", 8, 8, 5) + '</svg>inherited (germline) genetic test</span>'
          + "".join(f'<span><svg width="14" height="14">{status_mark(k, 7, 7, 5)}</svg>{e(v[0])}</span>' for k, v in STATUS.items())
          + "".join(f'<span><i class="sw" style="background:{c}"></i>{e(n)}</span>' for n, c in CLS.values())
          + "</div>")


# --- variant 1: tracks (cBioPortal patient-view style) -------------------------------------------------------------
def variant_tracks():
    W, L = 1320, 200
    ax = Axis(L + 10, W - 190)
    y = 30
    rows = []
    s = []
    # tests track
    s.append(f'<text x="{L - 10}" y="{y + 16}" text-anchor="end" font-size="12.5" font-weight="600" fill="var(--text-primary)">Tests</text>')
    placed = []
    for t in sorted(TESTS, key=lambda t: t["date"]):
        x = ax.x(t["date"])
        row = 0
        while any(abs(px - x) < 30 and pr == row for px, pr in placed):
            row += 1
        placed.append((x, row))
        cy = y + 12 + row * 20
        s.append(glyph(t["kind"], x, cy) + f'<text x="{x + 10:.1f}" y="{cy + 4}" font-size="11" font-weight="700" fill="var(--text-primary)">{t["id"]}</text>')
    for d, what, _ in UNTESTED:
        x = ax.x(d)
        s.append(f'<text x="{x:.1f}" y="{y + 16}" text-anchor="middle" font-size="13" fill="var(--text-muted)">?</text>')
    y += 96
    s.append(f'<line x1="{L}" x2="{W - 190}" y1="{y - 6}" y2="{y - 6}" stroke="var(--grid)"/>')
    # marker rows
    for key, label in MARKERS:
        s.append(f'<text x="{L - 10}" y="{y + 15}" text-anchor="end" font-size="12" fill="var(--text-secondary)">{e(label)}</text>')
        pts = sorted(((t["date"], t["res"][key]) for t in TESTS if key in t["res"]), key=lambda p: p[0])
        for i, (d, (st, txt)) in enumerate(pts):
            x0 = ax.x(d)
            x1 = ax.x(pts[i + 1][0]) if i + 1 < len(pts) else ax.x(C.today)
            col = STATUS[st][1]
            s.append(f'<rect x="{x0:.1f}" y="{y + 7}" width="{max(2, x1 - x0):.1f}" height="12" rx="3" fill="{col}" opacity="0.18"/>')
        for d, (st, txt) in pts:
            s.append(status_mark(st, ax.x(d), y + 13))
        if pts:   # latest known status, written at the right edge
            st, txt = pts[-1][1]
            s.append(f'<text x="{W - 182}" y="{y + 17}" font-size="11.5" fill="var(--text-primary)">{e(txt)}</text>')
        else:
            s.append(f'<text x="{W - 182}" y="{y + 17}" font-size="11.5" fill="var(--text-muted)">not tested</text>')
        y += 26
    s.append(f'<text x="{W - 182}" y="{y - 26 * len(MARKERS) - 14}" font-size="10.5" font-weight="700" fill="var(--text-secondary)">LATEST RESULT</text>')
    y += 8
    s.append(f'<line x1="{L}" x2="{W - 190}" y1="{y - 6}" y2="{y - 6}" stroke="var(--grid)"/>')
    # treatments
    s.append(f'<text x="{L - 10}" y="{y + 16}" text-anchor="end" font-size="12.5" font-weight="600" fill="var(--text-primary)">Treatments</text>')
    tops = []
    for name, cls, d0, d1, basis, src in TREAT:
        x0, x1 = ax.x(d0), ax.x(d1)
        row = 0
        while any(r == row and not (x0 > b + 150 or x1 < a - 4) for a, b, r in tops):
            row += 1
        tops.append((x0, x1, row))
        by = y + 6 + row * 36
        s.append(f'<rect x="{x0:.1f}" y="{by}" width="{max(3, x1 - x0):.1f}" height="11" rx="4" fill="{CLS[cls][1]}"/>')
        tx0, anc = label_pos(x0, x1, max(len(name) * 6.6, len(basis) * 5.4), W - 195)
        s.append(f'<text x="{tx0:.1f}" y="{by + 23}" text-anchor="{anc}" font-size="11.5" font-weight="600" fill="var(--text-primary)">{e(name)}</text>'
                 f'<text x="{tx0:.1f}" y="{by + 35}" text-anchor="{anc}" font-size="10" fill="var(--text-secondary)">{e(basis)}</text>')
        if src:   # dashed link up to the test it rested on
            tx = ax.x(next(t["date"] for t in TESTS if t["id"] == src))
            if cls in LINK:
                s.append(f'<path d="M{tx:.1f},{48} C{tx:.1f},{by - 60} {x0 + 4:.1f},{by - 40} {x0 + 4:.1f},{by}" fill="none" '
                         f'stroke="{CLS[cls][1]}" stroke-width="1.8" stroke-dasharray="4 3"/>')
    y += 6 + (max(r for _, _, r in tops) + 1) * 36 + 10
    grid = ax.svg_grid(20, y - 4, y + 12)
    H = y + 22
    svg = f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Biomarker tracks and treatments">{grid}{"".join(s)}</svg>'
    return svg


def tests_key():
    items = [(t["date"], f'<tr><td class="num">{t["id"]}</td><td class="n">{common.fmt(t["date"])}</td>'
                         f'<td><svg width="16" height="16">{glyph(t["kind"], 8, 8, 5)}</svg> <b>{e(t["title"])}</b> <span class="muted">{e(t["lab"])}</span></td>'
                         f'<td>{e(t["summary"])}</td></tr>') for t in TESTS]
    items += [(d, f'<tr><td class="num">?</td><td class="n">{common.fmt(d)}</td><td><b>{e(w)}</b></td><td class="muted">{e(n)}</td></tr>')
              for d, w, n in UNTESTED]
    rows = "".join(r for _, r in sorted(items))
    return f'<table class="key"><thead><tr><th>#</th><th>Date</th><th>Test</th><th>Result</th></tr></thead><tbody>{rows}</tbody></table>'


# --- variant 3: mirrored timeline (findings above, treatments below) ---------------------------------------------
def variant_mirror():
    W, L = 1320, 20
    ax = Axis(L + 10, W - 20, early_share=0.24)
    axis_y = 330
    s = []
    # cards above: tests + untested progressions, placed left to right in date order on two tiers
    items = [(t["date"], "test", t) for t in TESTS] + [(d, "gap", (w, n)) for d, w, n in UNTESTED]
    items.sort(key=lambda it: it[0])
    cw, ch = 150, 104
    slots = []
    last_right = {0: -1e9, 1: -1e9}
    for d, kind, obj in items:
        x = ax.x(d)
        tier = 0 if last_right[0] <= last_right[1] else 1
        cx = max(x - cw / 2, last_right[tier] + 8, 10)
        cx = min(cx, W - cw - 10)
        last_right[tier] = cx + cw
        cy = 22 + tier * (ch + 22)
        slots.append((d, kind, obj, x, cx, cy))
    anchor = {}
    for d, kind, obj, x, cx, cy in slots:
        s.append(f'<line x1="{cx + cw / 2:.1f}" y1="{cy + ch}" x2="{x:.1f}" y2="{axis_y - 8}" stroke="var(--guide)" stroke-width="1"/>')
        if kind == "test":
            t = obj
            anchor[t["id"]] = x
            lines = [f'{SHORT[k].rstrip(":")}: {v}' for k, (st, v) in t["res"].items()] or [t["summary"]]
            body = "".join(f'<tspan x="{cx + 10:.1f}" dy="13">{e(l)}</tspan>' for l in wrap_lines(lines, 26)[:4])
            s.append(f'<rect x="{cx:.1f}" y="{cy}" width="{cw}" height="{ch}" rx="7" fill="var(--surface-1)" stroke="var(--grid)"/>'
                     + glyph(t["kind"], cx + 14, cy + 15, 5)
                     + f'<text x="{cx + 25:.1f}" y="{cy + 19}" font-size="11" font-weight="700" fill="var(--text-primary)">{t["id"]} · {common.fmt(t["date"])}</text>'
                     f'<text x="{cx + 10:.1f}" y="{cy + 34}" font-size="10.5" font-weight="600" fill="var(--text-primary)">{e(t["title"][:28])}</text>'
                     f'<text x="{cx + 10:.1f}" y="{cy + 38}" font-size="10" fill="var(--text-secondary)">{body}</text>')
        else:
            w, n = obj
            body = "".join(f'<tspan x="{cx + 10:.1f}" dy="13">{e(l)}</tspan>' for l in wrap_lines([n], 26)[:4])
            s.append(f'<rect x="{cx:.1f}" y="{cy}" width="{cw}" height="{ch}" rx="7" fill="none" stroke="var(--text-muted)" stroke-dasharray="4 3"/>'
                     f'<text x="{cx + 10:.1f}" y="{cy + 19}" font-size="11" font-weight="700" fill="var(--text-secondary)">? · {common.fmt(d)}</text>'
                     f'<text x="{cx + 10:.1f}" y="{cy + 34}" font-size="10.5" font-weight="600" fill="var(--text-secondary)">{e(w)}</text>'
                     f'<text x="{cx + 10:.1f}" y="{cy + 38}" font-size="10" fill="var(--text-muted)">{body}</text>')
    # axis
    s.append(f'<line x1="{L}" x2="{W - 20}" y1="{axis_y}" y2="{axis_y}" stroke="var(--text-secondary)" stroke-width="1.5"/>')
    for yr, x in ax.ticks():
        s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{axis_y - 4}" y2="{axis_y + 4}" stroke="var(--text-secondary)"/>'
                 f'<text x="{x:.1f}" y="{axis_y + 17}" text-anchor="middle" font-size="11" fill="var(--text-secondary)">{yr}</text>')
    if ax.gap:
        g0, g1 = ax.gap
        s.append(f'<text x="{(g0 + g1) / 2:.1f}" y="{axis_y + 4}" text-anchor="middle" font-size="14" fill="var(--text-muted)">//</text>')
    # treatments below
    y0 = axis_y + 36
    tops = []
    for name, cls, d0, d1, basis, src in TREAT:
        x0, x1 = ax.x(d0), ax.x(d1)
        row = 0
        while any(r == row and not (x0 > b + 150 or x1 < a - 4) for a, b, r in tops):
            row += 1
        tops.append((x0, x1, row))
        by = y0 + row * 44
        col = CLS[cls][1]
        s.append(f'<rect x="{x0:.1f}" y="{by}" width="{max(3, x1 - x0):.1f}" height="12" rx="4" fill="{col}"/>'
                 + (lambda tx0, anc: f'<text x="{tx0:.1f}" y="{by + 25}" text-anchor="{anc}" font-size="11.5" font-weight="600" fill="var(--text-primary)">{e(name)}</text>'
                 f'<text x="{tx0:.1f}" y="{by + 38}" text-anchor="{anc}" font-size="10" fill="var(--text-secondary)">{e("Basis: " + basis)}</text>')(
                     *label_pos(x0, x1, max(len(name) * 6.6, (len(basis) + 7) * 5.4), W - 20)))
        if src and src in anchor:
            tx = anchor[src]
            strong = cls in LINK
            s.append(f'<path d="M{tx:.1f},{axis_y - 6} C{tx:.1f},{axis_y + 18} {x0 + 3:.1f},{by - 22} {x0 + 3:.1f},{by}" fill="none" '
                     f'stroke="{col}" stroke-width="{2 if strong else 1.2}" opacity="{1 if strong else 0.7}"/>')
    y = y0 + (max(r for _, _, r in tops) + 1) * 44 + 14
    strip, h = ca_strip(ax, y, L, W - 20)
    s.append(strip)
    H = y + h + 6
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Findings above, treatments below, tumour marker at the bottom">{"".join(s)}</svg>'


def ca_strip(ax, y, x_left, x_right, h=120):
    """The tumour marker on the same broken time axis: line, upper limit of normal, first / highest / latest values labelled."""
    pts = [(d, v) for d, v, _ in timeline.ca_points()]
    M = C["tumor_marker"]
    left = SEGMENTS[-1][0].isoformat()
    top, bottom = y + 22, y + h - 16
    vmax = max(v for _, v in pts) * 1.1
    yv = lambda v: bottom - v / vmax * (bottom - top)
    s = [f'<line x1="{x_left}" x2="{x_right}" y1="{y}" y2="{y}" stroke="var(--grid)"/>',
         f'<text x="{x_left + 4}" y="{y + 15}" font-size="11.5" font-weight="600" fill="var(--text-primary)">{M["name"]} ({M["unit"]})</text>',
         f'<text x="{x_left + 108}" y="{y + 15}" font-size="10" fill="var(--text-secondary)">blood tumour marker · dashed line = upper limit of normal ({M["uln"]})</text>']
    for v in (0, 50, 100, 150):
        if v <= vmax:
            s.append(f'<line x1="{ax.x(left):.1f}" x2="{x_right}" y1="{yv(v):.1f}" y2="{yv(v):.1f}" stroke="var(--grid)" stroke-width="0.6"/>'
                     f'<text x="{ax.x(left) - 4:.1f}" y="{yv(v) + 3.5:.1f}" text-anchor="end" font-size="9.5" fill="var(--text-muted)">{v}</text>')
    s.append(f'<line x1="{ax.x(left):.1f}" x2="{x_right}" y1="{yv(M['uln']):.1f}" y2="{yv(M['uln']):.1f}" stroke="var(--text-muted)" stroke-dasharray="5 4"/>')
    path = "".join(f'{"L" if i else "M"}{ax.x(d):.1f},{yv(v):.1f}' for i, (d, v) in enumerate(pts))
    s.append(f'<path d="{path}" fill="none" stroke="var(--text-primary)" stroke-width="1.8" stroke-linejoin="round"/>')
    for yr, x in ax.ticks():   # repeat the year labels under the strip
        if yr >= SEGMENTS[-1][0].year + 1:
            s.append(f'<text x="{x:.1f}" y="{bottom + 13:.1f}" text-anchor="middle" font-size="10" fill="var(--text-secondary)">{yr}</text>')
    for p in dict.fromkeys([pts[0], max(pts, key=lambda p: p[1]), pts[-1]]):
        x, yy = ax.x(p[0]), yv(p[1])
        anc, dx = ("end", -7) if x > x_right - 120 else ("start", 7)
        s.append(f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="3.2" fill="var(--text-primary)"/>'
                 f'<text x="{x + dx:.1f}" y="{max(top + 8, yy - 5):.1f}" text-anchor="{anc}" font-size="10.5" font-weight="600" fill="var(--text-primary)" '
                 f'stroke="var(--surface-1)" stroke-width="3" paint-order="stroke">{p[1]:g} ({common.fmt(p[0])})</text>')
    if P.get("marker_gap_note") and len(SEGMENTS) > 1:
        a0, a1 = SEGMENTS[0]
        mid = P.get("marker_gap_note_date") or (a0 + (a1 - a0) / 2).isoformat()
        s.append(f'<text x="{ax.x(mid):.1f}" y="{(top + bottom) / 2 + 4:.1f}" text-anchor="middle" font-size="10" fill="var(--text-muted)">'
                 f'{e(P["marker_gap_note"])}</text>')
    return "".join(s), h


def label_pos(x0, x1, width, right):
    """Left-aligned under the bar start, unless that would run past the right edge: then right-aligned to the bar end."""
    return (x0, "start") if x0 + width <= right else (max(x1, x0 + 10), "end")


def wrap_lines(parts, width):
    out = []
    for p in parts:
        line = ""
        for w in p.split():
            if len(line) + len(w) + 1 > width and line:
                out.append(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        if line:
            out.append(line)
    return out


CSS = common.CSS + """
@page { size: Letter landscape; margin: 9mm 10mm 10mm; }
body, .viz-root { background: #fff; } .viz-root { padding: 0; font-size: 9pt; } .wrap { max-width: none; }
section.v { break-before: page; } section.v:first-of-type { break-before: auto; }
h1 { font-size: 15pt; margin: 0 0 1mm; } h2 { font-size: 12.5pt; margin: 0 0 1mm; border: 0; }
.sub { font-size: 8.4pt; color: var(--text-secondary); margin: 0 0 2mm; } .muted { color: var(--text-secondary); }
.legend { font-size: 8pt; gap: 1mm 4mm; margin: 1mm 0 2mm; } .legend svg { vertical-align: -3px; margin-right: 3px; }
table.key { font-size: 7.9pt; margin-top: 2mm; } table.key td, table.key th { padding: 0.8mm 1.4mm; } td.num { font-weight: 700; }
.eps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2.4mm; }
.card.ep { padding: 2mm 2.6mm; border-radius: 6px; font-size: 7.7pt; break-inside: avoid; line-height: 1.25; }
.ep-h { display: flex; gap: 2mm; align-items: flex-start; margin-bottom: 1.5mm; } .ep-n { background: var(--text-primary); color: #fff;
  border-radius: 50%; width: 5.5mm; height: 5.5mm; display: inline-flex; align-items: center; justify-content: center; font-weight: 700; flex: none; }
.ep-s { font-size: 7pt; text-transform: uppercase; letter-spacing: .04em; color: var(--text-muted); margin-top: 1.5mm; }
.ep ul { margin: 0.5mm 0 0; padding-left: 0; list-style: none; } .ep li { margin: 0.6mm 0; } .ep li svg { vertical-align: -2px; margin-right: 3px; }
.ep ul.given li::before { content: "▸ "; color: var(--text-secondary); } .ep li.untested { color: var(--text-muted); font-style: italic; }
.chips { display: flex; flex-wrap: wrap; gap: 1mm; margin-top: .5mm; } .chip { border: 1px solid var(--grid); border-radius: 10px; padding: 0 1.6mm;
  font-size: 7.5pt; display: inline-flex; align-items: center; gap: 1mm; } .why { margin: .5mm 0 0; line-height: 1.3; }
.note { font-size: 7.6pt; color: var(--text-muted); margin-top: 2mm; }
.alert { font-size: 8.2pt; border-left: 3px solid var(--series-4); background: #fdf6e6; padding: 1.5mm 3mm; margin: 2mm 0 1mm; }
"""


def main():
    body = (f'<section class="v"><h1>{e(P["title"])}</h1>'
            f'<p class="sub">{C.text("pathology_sub")}</p>'
            f'<h2>1. Test results over time</h2><p class="sub">{C.text("pathology_tracks")}</p>'
            f'{LEGEND}<div class="card">{variant_tracks()}</div>'
            + (f'<p class="alert">{C.text("pathology_alert")}</p>' if "pathology_alert" in C["texts"] else "") + '</section>'
            f'<section class="v"><h2>Tests in the records</h2>{tests_key()}</section>'
            f'<section class="v"><h2>2. What was learned, and what it led to</h2><p class="sub">{C.text("pathology_mirror")}</p>'
            f'{LEGEND}<div class="card">{variant_mirror()}</div>'
            f'<p class="note">{e(C.text("pathology_note"))}</p></section>')
    doc = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Pathology and treatment</title><style>{CSS}</style></head>'
           f'<body><div class="viz-root"><div class="wrap">{body}</div></div></body></html>')
    pdf = common.write_and_print("pathology_timeline", doc, f"pathology_timeline_{C.built}.pdf")
    print("built:", pdf.name, pdf.stat().st_size, "bytes")
    return pdf
