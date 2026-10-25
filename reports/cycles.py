"""Chemotherapy cycles: blood counts, liver tests and the tumour marker through each cycle of a regimen, with the doses given
or not given, side effects, and a summary of every cycle since the drug started.

A regimen comes from the case file (``cycles:``, see docs/case-file.md): the drug, its schedule (dose days in a cycle of
N days), the first day 1, and the record of doses. Lab values come from the published notes' lab tables (labs.py) and
the marker from the case's ``tumor_marker``. ``python -m reports cycles --discover`` proposes regimens from the notes.

The rule for doses: when the case lists ``infusions`` (from infusion or administration records), a scheduled dose with
no record was not given. Without that list, scheduled doses are shown as not confirmed, never as given. When the records
start partway through (``infusion_records_from``), doses before that date are not confirmed either."""
import html
import re
from datetime import date, timedelta

import yaml

from . import common, labs

e = html.escape
D = common.D
C = common.case()

# key: (label, unit, low, high, CTCAE v5.0 grade cut-offs, lab-table row pattern, unit pattern). Low-count grades are the
# values below which grades 2, 3 and 4 begin (grade 1 starts below the normal range); "x" marks multiples of the upper
# limit for raised liver enzymes. Ranges and row patterns can be overridden in the case (cycles_tests).
TESTS = {
    "WBC": ("White blood cells", "×10³/µL", 4.5, 11.0, ("low", 3.0, 2.0, 1.0), r"WBC\b", r"x 10\^3/uL"),
    "ANC": ("Neutrophils (ANC)", "×10³/µL", 1.5, 7.5, ("low", 1.5, 1.0, 0.5), r"Neu # \(ANC\)", r"x 10\^3/uL"),
    "RBC": ("Red blood cells", "×10⁶/µL", 4.2, 5.4, None, r"RBC\b", r"x 10\^6/uL"),
    "HGB": ("Hemoglobin", "g/dL", 12.0, 15.5, ("low", 10.0, 8.0, None), r"HGB\b", r"g/dL"),
    "PLT": ("Platelets", "×10³/µL", 150, 400, ("low", 75, 50, 25), r"PLT\b", r"x 10\^3/uL"),
    "ALT": ("ALT (liver)", "U/L", 0, 33, ("x", 3, 5, 20), r"ALT/SGPT", r"U/L"),
    "AST": ("AST (liver)", "U/L", 0, 32, ("x", 3, 5, 20), r"AST/SGOT", r"U/L"),
}
for _k, _v in C.get("cycles_tests", {}).items():
    TESTS[_k] = tuple(_v[i] if i < len(_v) and _v[i] is not None else (TESTS.get(_k) or (None,) * 7)[i] for i in range(7))
PANELS = [["WBC", "ANC"], ["RBC"], ["HGB"], ["PLT"], ["ALT", "AST"]]
SHORT = {"WBC": "White cells", "ANC": "Neutrophils", "ALT": "ALT", "AST": "AST"}   # names in two-series panel titles
BASELINE_DAYS = 3   # a lab drawn up to this many days before a day 1 (with none on day 1) is that cycle's pre-dose value
SHOW_CYCLES = 4     # cycles shown in the calendar, overlays, summary and side effects: the latest, ending with the current one


def grade(key, v):
    """CTCAE v5.0 grade (0-4) for a value, by the cut-offs in TESTS."""
    _, _, lo, hi, g, *_ = TESTS[key]
    if not g:
        return 0
    if g[0] == "low":
        if v >= lo:
            return 0
        return max([1] + [i + 2 for i, t in enumerate(g[1:]) if t is not None and v < t])
    if v <= hi:
        return 0
    return max([1] + [i + 2 for i, m in enumerate(g[1:]) if m is not None and v > m * hi])


# --- the regimen and its cycles ------------------------------------------------------------------------------------------
class Regimen:
    def __init__(self, r):
        self.r, self.drug = r, r["drug"]
        s = r["schedule"]
        self.length, self.days = int(s["length"]), [int(d) for d in s["days"]]
        self.start = D(r["start"])
        self.today = D(C.today)
        self.ongoing = not r.get("end") or r["end"] == C.today
        self.end = self.today if self.ongoing else D(r["end"])
        self.has_records = "infusions" in r
        self.records_from = D(r["infusion_records_from"]) if r.get("infusion_records_from") else self.start
        self.given = {D(x["date"]): x for x in r.get("infusions") or []}
        self.not_given = {D(d): why for d, why in r.get("not_given", [])}
        self.dose_levels = sorted((D(d), lab) for d, lab in r.get("doses", []))
        # Cycles follow each other every `length` days; a listed day 1 (a cycle that started late or early) replaces the
        # scheduled one it falls nearest, and later cycles follow it.
        anchors = sorted(D(d) for d in r.get("day1", []) if D(d) > self.start)
        starts, step = [self.start], timedelta(days=self.length)
        while True:
            nxt = starts[-1] + step
            if anchors and anchors[0] < nxt + step / 2:
                nxt = anchors.pop(0)
            if nxt > self.end:
                break
            starts.append(nxt)
        self.cycles = [Cycle(self, i + 1, c) for i, c in enumerate(starts)]
        # the cycles the report tracks: the latest `show_cycles`, ending with the one in progress (numbers still count
        # from the first dose); a long regimen would otherwise make every page grow without bound
        n = int(r.get("show_cycles", C.get("cycles_show", SHOW_CYCLES)))
        self.shown = self.cycles[-n:] if n > 0 else list(self.cycles)

    def dose_on(self, d):
        cur = None
        for since, lab in self.dose_levels:
            if since <= d:
                cur = lab
        return cur

    def cycle_of(self, d):
        """The cycle a date falls in (a date just before the first day 1 belongs to cycle 1)."""
        for c in self.cycles:
            if c.start <= d <= c.last:
                return c
        first = self.cycles[0]
        return first if first.start - timedelta(days=BASELINE_DAYS) <= d < first.start else None

    def assign(self, d, series):
        """(cycle, day) for a lab date: its own cycle, except that the last draw shortly before a day 1 with no draw of its
        own is that next cycle's pre-dose value (day 0)."""
        for c in self.cycles:
            if c.start - timedelta(days=BASELINE_DAYS) <= d < c.start and c.start.isoformat() not in series:
                if not any(c.start > D(o) > d for o in series):
                    return c, 0
        c = self.cycle_of(d)
        return (c, c.day(d)) if c else (None, None)

    def current(self):
        return next((c for c in self.cycles if c.start <= self.today <= c.last), None)

    def latest_complete(self):
        done = [c for c in self.cycles if c.last < self.today]
        return done[-1] if done else None


class Cycle:
    def __init__(self, reg, n, start):
        self.reg, self.n, self.start = reg, n, start
        self.last = start + timedelta(days=reg.length - 1)

    def day(self, d):
        return (d - self.start).days + 1

    def date(self, day):
        return self.start + timedelta(days=day - 1)

    def doses(self):
        """[(day, date, status, detail)] for each scheduled dose; status given | not given | not confirmed | expected."""
        out = []
        for day in self.reg.days:
            d = self.date(day)
            if d > self.reg.end and not self.reg.ongoing:
                continue
            rec = self.reg.given.get(d) or next((v for k, v in self.reg.given.items() if abs((k - d).days) <= 1), None)
            if rec:
                detail = rec.get("dose") or self.reg.dose_on(d) or ""
                out.append((day, d, "given", f"{detail} ({rec['note']})" if rec.get("note") else detail))
            elif d >= self.reg.today:
                out.append((day, d, "expected", "expected if on schedule"))
            elif d in self.reg.not_given:
                out.append((day, d, "not given", self.reg.not_given[d]))
            elif self.reg.has_records and d >= self.reg.records_from:
                out.append((day, d, "not given", "no infusion record"))
            elif self.reg.has_records:
                out.append((day, d, "not confirmed", "before the infusion records start"))
            else:
                out.append((day, d, "not confirmed", "no infusion record yet"))
        return out

    def status(self):
        st = [s for _, _, s, _ in self.doses()]
        if self.last >= self.reg.today:
            return "in progress"
        if not self.reg.has_records or "not confirmed" in st:
            return "doses not confirmed"
        given = st.count("given")
        if given == len(st):
            return "completed"
        return f"completed, {given} of {len(st)} doses given" if given else "no doses given"


# --- data ---------------------------------------------------------------------------------------------------------------
def lab_data():
    tests = {k: [v[5], v[6]] for k, v in TESTS.items() if v[5]}
    data, _ = labs.parse(tests)
    data["CA"] = dict(C.marker)
    return data


def in_cycle(reg, c, series):
    """[(day, value, iso date)] for a cycle; a lab just before day 1 counts as day 0 when day 1 has none."""
    out = []
    for iso, v in sorted(series.items()):
        cy, day = reg.assign(D(iso), series)
        if cy is c:
            out.append((day, v, iso))
    return out


# --- drawing -----------------------------------------------------------------------------------------------------------
STATUS_MARK = {"given": "●", "not given": "✕", "not confirmed": "?", "expected": "○"}
CYCLE_COLORS = ["var(--series-1)", "var(--series-3)", "var(--series-5)", "var(--series-4)", "var(--series-6)", "var(--series-2)"]


def axis(reg, W, L, R):
    return lambda day: L + (W - L - R) * day / reg.length


def panel(reg, c, cur, keys, data, W=600, H=128):
    """One small chart: the detail cycle's values (solid) and the cycle in progress (dashed), on a day-of-cycle axis."""
    L, R, T, B = 46, 14, 26, 22
    x = axis(reg, W, L, R)
    series = [(k, in_cycle(reg, c, data[k]), in_cycle(reg, cur, data[k]) if cur else []) for k in keys]
    vals = [v for _, a, b in series for _, v, _ in a + b]
    lo, hi = (0, C["tumor_marker"]["uln"]) if keys[0] == "CA" else (TESTS[keys[0]][2], TESTS[keys[0]][3])
    vmax = max([hi * 1.15] + [v * 1.12 for v in vals])
    y = lambda v: T + (H - T - B) * (1 - v / vmax)
    s = []
    if keys[0] == "CA":
        label = C["tumor_marker"]["name"]
    elif len(keys) == 1:
        label = TESTS[keys[0]][0]
    else:   # two series: short names, and say when the second has no complete row in this cycle
        a, b = (SHORT.get(k, k) for k in keys[:2])
        label = f"{a} (solid), {b.lower() if b[1:].islower() else b} (dashed{'; none this cycle' if not series[1][1] else ''})"
    unit = C["tumor_marker"]["unit"] if keys[0] == "CA" else TESTS[keys[0]][1]
    s.append(f'<text x="{L}" y="13" font-size="12" font-weight="650" fill="var(--text-primary)">{e(label)}</text>'
             f'<text x="{W - R}" y="13" text-anchor="end" font-size="10" fill="var(--text-secondary)">{e(unit)} · normal '
             f'{"≤ " + format(hi, "g") if not lo else format(lo, "g") + "–" + format(hi, "g")}</text>')
    s.append(f'<rect x="{L}" y="{y(hi):.1f}" width="{W - L - R}" height="{y(lo) - y(hi):.1f}" fill="var(--series-1)" opacity="0.08"/>')
    g = TESTS[keys[0]][4] if keys[0] != "CA" else None
    if g:   # the grade 2 and grade 3 lines, where they fall inside the plot
        for gi, t in ((2, g[1]), (3, g[2])):
            if t is None:
                continue
            tv = t if g[0] == "low" else t * hi
            if tv < vmax:
                ty = y(tv) - 2 if gi == 2 else y(tv) + 8   # grade 2 above its line, grade 3 below: close lines stay readable
                s.append(f'<line x1="{L}" x2="{W - R}" y1="{y(tv):.1f}" y2="{y(tv):.1f}" stroke="var(--series-4)" stroke-dasharray="4 3"/>'
                         f'<text x="{W - R - 2}" y="{ty:.1f}" text-anchor="end" font-size="8" fill="var(--text-secondary)">grade {gi}</text>')
    for v in sorted({0, lo, hi} - {0} if lo else {hi}):
        s.append(f'<text x="{L - 5}" y="{y(v) + 3:.1f}" text-anchor="end" font-size="9" fill="var(--text-muted)">{v:g}</text>')
    for day in reg.days:
        s.append(f'<line x1="{x(day):.1f}" x2="{x(day):.1f}" y1="{T - 4}" y2="{H - B}" stroke="var(--guide)"/>')
    for day in range(0, reg.length + 1, 7):
        s.append(f'<text x="{x(day):.1f}" y="{H - 8}" text-anchor="middle" font-size="9" fill="var(--text-muted)">{day or "pre"}</text>')
    s.append(f'<line x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}" stroke="var(--grid)"/>')
    for i, (k, pts, now) in enumerate(series):
        dash = "" if i == 0 else ' stroke-dasharray="5 3"'
        for p, faint in ((now, True), (pts, False)):
            if not p:
                continue
            col = "var(--text-muted)" if faint else "var(--text-primary)"
            style = ' stroke-dasharray="2 3"' if faint else dash
            op = ' opacity="0.7"' if faint else ""
            path = "".join(f'{"L" if j else "M"}{x(dd):.1f},{y(v):.1f}' for j, (dd, v, _) in enumerate(p))
            s.append(f'<path d="{path}" fill="none" stroke="{col}" stroke-width="{1.2 if faint else 1.8}"{style}/>')
            for dd, v, iso in p:
                gr = grade(k, v) if k != "CA" else (1 if v > hi else 0)
                fill = "var(--series-2)" if gr else col
                s.append(f'<circle cx="{x(dd):.1f}" cy="{y(v):.1f}" r="{3.4 if not faint else 2.6}" fill="{fill}"{op}>'
                         f'<title>{e(k)} {v:g} on {common.fmt(iso)}</title></circle>')
                if not faint:   # first series labelled above its points, the second below
                    tag = f" G{gr}" if gr and k != "CA" else ""
                    ly = y(v) - 5 if i == 0 else y(v) + 13
                    s.append(f'<text x="{x(dd) + 5:.1f}" y="{ly:.1f}" font-size="9.5" font-weight="600" fill="var(--text-primary)" '
                             f'stroke="var(--surface-1)" stroke-width="3" paint-order="stroke">{v:g}{tag}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{e(label)} through cycle {c.n}">{"".join(s)}</svg>'


def dose_strip(reg, c, cur, effects, W=1230):
    """Dose days of the detail cycle (and the cycle in progress) with their status, and side effects pinned to their day."""
    L, R = 46, 14
    x = axis(reg, W, L, R)
    s, rows = [], [(c, 22)] + ([(cur, 74)] if cur else [])
    for cy, yy in rows:
        faint = cy is not c
        s.append(f'<text x="{L - 6}" y="{yy + 4}" text-anchor="end" font-size="11" font-weight="650" '
                 f'fill="{"var(--text-secondary)" if faint else "var(--text-primary)"}">C{cy.n}</text>'
                 f'<line x1="{L}" x2="{W - R}" y1="{yy}" y2="{yy}" stroke="var(--grid)"/>')
        for day, d, st, det in cy.doses():
            col = {"given": "var(--series-3)", "not given": "var(--series-2)", "not confirmed": "var(--text-secondary)",
                   "expected": "var(--text-muted)"}[st]
            s.append(f'<text x="{x(day):.1f}" y="{yy + 5}" text-anchor="middle" font-size="14" fill="{col}">{STATUS_MARK[st]}</text>'
                     f'<text x="{x(day) + 9:.1f}" y="{yy + 4}" font-size="9.5" fill="var(--text-primary)">D{day} {e(common.fmt(d.isoformat()))}</text>'
                     f'<text x="{x(day) + 9:.1f}" y="{yy + 15}" font-size="9" fill="var(--text-secondary)">{e(st)}{": " + e(det) if det and st != "expected" else ""}</text>')
        if cy is cur:
            t = (reg.today - cy.start).days + 1
            s.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{yy - 12}" y2="{yy + 12}" stroke="var(--series-2)" stroke-width="1.5"/>'
                     f'<text x="{x(t):.1f}" y="{yy - 15}" text-anchor="middle" font-size="9" fill="var(--series-2)">today, day {t}</text>')
    row_y = {cy.n: yy for cy, yy in rows}
    for i, (d, txt, _) in enumerate(effects):
        cy = reg.cycle_of(D(d))
        if cy is None or cy.n not in row_y:
            continue
        xx, yy = x(cy.day(D(d))), row_y[cy.n] + 30
        s.append(f'<circle cx="{xx:.1f}" cy="{yy - 3.5:.1f}" r="6.5" fill="var(--series-5)" opacity="{1 if cy is c else 0.55}"/>'
                 f'<text x="{xx:.1f}" y="{yy:.1f}" text-anchor="middle" font-size="9" font-weight="700" fill="#fff">{i + 1}</text>')
    H = rows[-1][1] + 40
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Doses and side effects">{"".join(s)}</svg>'


def calendar(reg, data):
    """Every cycle as a row of days: dose days by status, lab draws, and the lowest counts of the cycle."""
    cw, L, top = 21, 150, 30
    W = L + cw * (reg.length + 1) + 430
    s = [f'<text x="{L + cw * (d + .5):.1f}" y="{top - 8}" text-anchor="middle" font-size="9" fill="var(--text-muted)">{d}</text>'
         for d in [0] + list(range(1, reg.length + 1)) if d == 0 or d in reg.days or d % 7 == 0]
    s.append(f'<text x="{L + cw * .5:.1f}" y="{top - 18}" text-anchor="middle" font-size="9" fill="var(--text-muted)">pre</text>'
             f'<text x="{W - 425}" y="{top - 8}" font-size="9.5" font-weight="600" fill="var(--text-secondary)">Lowest values (day) · grade</text>')
    drawn = {}
    for iso in data["WBC"]:
        cy, day = reg.assign(D(iso), data["WBC"])
        if cy:
            drawn.setdefault(cy.n, set()).add(day)
    for i, c in enumerate(reg.shown):
        y = top + i * 26
        s.append(f'<text x="{L - 8}" y="{y + 14}" text-anchor="end" font-size="11" font-weight="650" fill="var(--text-primary)">Cycle {c.n}</text>'
                 f'<text x="{L - 8}" y="{y + 24}" text-anchor="end" font-size="8.5" fill="var(--text-secondary)">from {e(common.fmt(c.start.isoformat()))}</text>')
        for day in range(0, reg.length + 1):
            d = c.date(day)
            xx = L + cw * day
            fill, mark = "var(--surface-1)", ""
            dose = next((x for x in c.doses() if x[0] == day), None)
            if dose:
                fill = {"given": "var(--series-3)", "not given": "var(--series-2)", "not confirmed": "var(--guide)",
                        "expected": "var(--surface-1)"}[dose[2]]
                mark = STATUS_MARK[dose[2]] if dose[2] != "given" else ""
            expected = bool(dose and dose[2] == "expected")
            stroke = "var(--text-muted)" if expected else "var(--grid)"
            dash = ' stroke-dasharray="2 2"' if expected else ""
            what = ": " + e(dose[2]) if dose else ""
            s.append(f'<rect x="{xx + 1}" y="{y + 2}" width="{cw - 2}" height="18" rx="3" fill="{fill}" stroke="{stroke}"{dash}>'
                     f'<title>{e(common.fmt(d.isoformat()))}{what}</title></rect>')
            if mark:
                s.append(f'<text x="{xx + cw / 2:.1f}" y="{y + 15}" text-anchor="middle" font-size="10" fill="var(--text-primary)">{mark}</text>')
            if day in drawn.get(c.n, ()):
                s.append(f'<circle cx="{xx + cw / 2:.1f}" cy="{y + 23.5}" r="1.8" fill="var(--text-primary)"/>')
            if d == reg.today:
                s.append(f'<rect x="{xx}" y="{y}" width="{cw}" height="22" fill="none" stroke="var(--series-2)" stroke-width="1.6" rx="3"/>')
        lows = []
        for k in ("ANC", "WBC", "PLT", "HGB"):
            p = [(dd, v) for dd, v, _ in in_cycle(reg, c, data[k])]
            if p:
                dd, v = min(p, key=lambda t: t[1])
                gr = grade(k, v)
                lows.append(f"{k} {v:g} (d{dd}){' G' + str(gr) if gr else ''}")
        s.append(f'<text x="{W - 425}" y="{y + 14}" font-size="9.5" fill="var(--text-primary)">{e(" · ".join(lows) or "no labs")}</text>')
    H = top + 26 * len(reg.shown) + 8
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Every cycle by day">{"".join(s)}</svg>'


def overlay(reg, key, data, W=600, H=150):
    """One test across every cycle, on the same day-of-cycle axis: does the low point deepen from cycle to cycle?"""
    L, R, T, B = 46, 70, 26, 22
    x = axis(reg, W, L, R)
    lo, hi = TESTS[key][2], TESTS[key][3]
    lines = [(c, in_cycle(reg, c, data[key])) for c in reg.shown]
    vmax = max([hi * 1.15] + [v * 1.12 for _, p in lines for _, v, _ in p])
    y = lambda v: T + (H - T - B) * (1 - v / vmax)
    s = [f'<text x="{L}" y="13" font-size="12" font-weight="650" fill="var(--text-primary)">{e(TESTS[key][0])}</text>'
         f'<text x="{W - R}" y="13" text-anchor="end" font-size="10" fill="var(--text-secondary)">{e(TESTS[key][1])}</text>',
         f'<rect x="{L}" y="{y(hi):.1f}" width="{W - L - R}" height="{y(lo) - y(hi):.1f}" fill="var(--series-1)" opacity="0.08"/>',
         f'<line x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}" stroke="var(--grid)"/>']
    for v in ([lo, hi] if lo else [hi]):
        s.append(f'<text x="{L - 5}" y="{y(v) + 3:.1f}" text-anchor="end" font-size="9" fill="var(--text-muted)">{v:g}</text>')
    for day in reg.days:
        s.append(f'<line x1="{x(day):.1f}" x2="{x(day):.1f}" y1="{T - 4}" y2="{H - B}" stroke="var(--guide)"/>')
    for day in range(7, reg.length + 1, 7):
        s.append(f'<text x="{x(day):.1f}" y="{H - 8}" text-anchor="middle" font-size="9" fill="var(--text-muted)">{day}</text>')
    s.append(f'<text x="{x(0):.1f}" y="{H - 8}" text-anchor="middle" font-size="9" fill="var(--text-muted)">pre</text>')
    # colours go to the latest cycles with a course to compare (two values or more), and the cycle in progress
    cur = reg.current()
    shown = [(c, p) for c, p in lines if len(p) > 1 or (p and c is cur)][-len(CYCLE_COLORS):]
    for i, (c, p) in enumerate(shown):
        if not p:
            continue
        col = CYCLE_COLORS[i]
        path = "".join(f'{"L" if j else "M"}{x(dd):.1f},{y(v):.1f}' for j, (dd, v, _) in enumerate(p))
        s.append(f'<path d="{path}" fill="none" stroke="{col}" stroke-width="2"/>')
        for dd, v, iso in p:
            s.append(f'<circle cx="{x(dd):.1f}" cy="{y(v):.1f}" r="3.2" fill="{col}" stroke="var(--surface-1)" stroke-width="1.5">'
                     f'<title>Cycle {c.n} day {dd}: {v:g} ({common.fmt(iso)})</title></circle>')
    # direct labels at the right edge, spread so they don't collide
    ends = sorted(((y(p[-1][1]), c, CYCLE_COLORS[i]) for i, (c, p) in enumerate(shown) if p), key=lambda t: t[0])
    last = -99
    for yy, c, col in ends:
        yy = max(yy, last + 11)
        last = yy
        s.append(f'<text x="{W - R + 6}" y="{yy + 3:.1f}" font-size="9.5" font-weight="600" fill="var(--text-primary)">'
                 f'<tspan fill="{col}">●</tspan> C{c.n}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{e(TESTS[key][0])}, every cycle">{"".join(s)}</svg>'


# --- tables and text -----------------------------------------------------------------------------------------------------
def window_title(reg):
    """The heading for the tracked cycles, saying how many earlier ones are left out."""
    a, b = reg.shown[0], reg.shown[-1]
    if a.n == 1:
        return f"Every cycle since {common.fmt(a.start.isoformat())}"
    return (f"The last {len(reg.shown)} cycles ({a.n}–{b.n}, from {common.fmt(a.start.isoformat())}); cycles 1–{a.n - 1} "
            f"from {common.fmt(reg.start.isoformat())} are not shown")


def summary_table(reg, data, effects):
    rows = []
    for c in reversed(reg.shown):
        ds = c.doses()
        given = sum(1 for x in ds if x[2] == "given")
        doses = " ".join(f"D{day}{STATUS_MARK[st]}" for day, _, st, _ in ds)
        lows = []
        for k in ("ANC", "WBC", "HGB", "PLT"):
            p = [(dd, v) for dd, v, _ in in_cycle(reg, c, data[k])]
            if p:
                dd, v = min(p, key=lambda t: t[1])
                lows.append(f"{k} {v:g} d{dd}" + (f" <b>G{grade(k, v)}</b>" if grade(k, v) else ""))
        alt = [(dd, v) for dd, v, _ in in_cycle(reg, c, data["ALT"])]
        if alt:
            dd, v = max(alt, key=lambda t: t[1])
            lows.append(f"ALT peak {v:g} d{dd}" + (f" <b>G{grade('ALT', v)}</b>" if grade("ALT", v) else ""))
        ca = in_cycle(reg, c, data["CA"])
        ca_txt = " → ".join(f"{v:g}" for _, v, _ in ca) if ca else "–"
        se = "; ".join(f"[{i + 1}]" for i, (d, _, _) in enumerate(effects) if reg.cycle_of(D(d)) is c)
        dose = reg.dose_on(c.start) or ""
        rows.append(f'<tr><td class="n"><b>Cycle {c.n}</b><br>{e(common.fmt(c.start.isoformat()))} – {e(common.fmt(c.last.isoformat()))}</td>'
                    f'<td>{e(c.status())}</td><td>{e(doses)}<br><span class="m">{given} of {len(ds)} recorded as given</span></td>'
                    f'<td>{e(dose)}</td><td>{" · ".join(lows) or "–"}</td><td>{e(ca_txt)}</td><td>{se or "–"}</td></tr>')
    return ('<table class="sum"><thead><tr><th>Cycle</th><th>Status</th><th>Doses</th><th>Dose level</th><th>Lowest counts (day), peak ALT</th>'
            f'<th>{e(C["tumor_marker"]["name"])}</th><th>Side effects</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')


LOG_TITLE = re.compile(r"^Symptom log: (?P<drug>.+?), cycle \d+", re.M)
LOG_ROW = re.compile(r"^\d+ \| (?P<date>\d{4}-\d{2}-\d{2}) \| [A-Z][a-z]{2}\b(?P<rest>.*)$")
NO = {"no", "none", "-", "n"}   # "no" answers are left out; a 0 on a 0–3 scale is kept (it is an answer)


FEVER_F = 100.4   # a temperature at or above this is always named in the summary


def family_log(reg):
    """{iso date: {column header: value}} from the family's symptom log sheets in the published notes (symptom_log.py
    writes them; the family fills them in and keeps them with the records). Read on every build, so new entries need no
    case edits. A later sheet wins for the same date. Blank cells and "no" answers are left out."""
    out = {}
    for f in sorted(C.notes.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = LOG_TITLE.search(text)
        if not m or m.group("drug").strip().lower() != reg.drug.lower():
            continue
        head = None
        for line in text.splitlines():
            if line.startswith("Day | Date |"):
                head = [h.strip() for h in line.split(" | ")]
                continue
            r = LOG_ROW.match(line)
            if not (head and r):
                continue
            cells = [c.strip() for c in line.split(" | ")]
            row = {h: v for h, v in zip(head[3:], cells[3:])
                   if v and v.lower() not in NO and not (h.lower().startswith("dose") and re.fullmatch(r"day \d+ dose", v))}
            if row:
                out[r.group("date")] = row
    return out


def _day_list(days):
    """[8, 9, 10, 12] -> "days 8–10 and 12"."""
    runs, days = [], sorted(days)
    for d in days:
        if runs and d == runs[-1][1] + 1:
            runs[-1][1] = d
        else:
            runs.append([d, d])
    text = [f"{a}–{b}" if b > a else f"{a}" for a, b in runs]
    return ("day " if len(days) == 1 else "days ") + (", ".join(text[:-1]) + " and " + text[-1] if len(text) > 1 else text[0])


def _label(h):
    name = re.sub(r"\s*\(.*?\)", "", h).strip()
    return name.lower() if name[1:].islower() else name


def log_summaries(reg, logged):
    """[(iso date, text)]: one rule-based summary of the family log per cycle the report tracks, dated to the cycle's
    first logged day. It names the days logged (blank days are not "no symptoms"), the highest temperature (and any at or
    above FEVER_F), each "yes" symptom, the range of each 0–3 score, and each other entry, with their days."""
    out = []
    for c in reg.shown:
        days = {c.day(D(iso)): row for iso, row in logged.items() if reg.cycle_of(D(iso)) is c}
        if not days:
            continue
        parts, by = [], {}
        for day, row in days.items():
            for h, v in row.items():
                by.setdefault(h, []).append((day, v))
        for h, vals in by.items():
            if h.startswith("Temp"):
                nums = [(d, float(re.sub(r"[^\d.]", "", v))) for d, v in vals if re.search(r"\d", v)]
                if nums:
                    d, top = max(nums, key=lambda t: t[1])
                    fevers = [d for d, t in nums if t >= FEVER_F]
                    parts.append(f"highest temperature {top:g} °F (day {d})"
                                 + (f"; fever ≥{FEVER_F:g} °F on {_day_list(fevers)}" if fevers else ""))
            elif h.lower().startswith("dose"):
                parts += [f"dose day {d}: {v}" for d, v in vals]
            elif all(v.lower() in ("yes", "y") for _, v in vals):
                parts.append(f"{_label(h)} ({_day_list(d for d, _ in vals)})")
            elif "(0–3)" in h or "(0-3)" in h:
                nums = [(d, int(v)) for d, v in vals if v.isdigit()]
                if nums:
                    lo, hi = min(n for _, n in nums), max(n for _, n in nums)
                    peak = [d for d, n in nums if n == hi]
                    parts.append(f"{_label(h)} {lo}–{hi}/3 (highest {_day_list(peak)})" if hi > lo else f"{_label(h)} {hi}/3 ({_day_list(d for d, _ in nums)})")
            else:
                groups = {}
                for d, v in vals:
                    groups.setdefault(v, []).append(d)
                for v, ds in groups.items():
                    lead = "" if h.lower().startswith(("other", "notes")) else f"{_label(h)}: "
                    parts.append(f"{lead}{v[0].lower() + v[1:] if v[1:2].islower() else v} ({_day_list(ds)})")
        first = min(iso for iso in logged if reg.cycle_of(D(iso)) is c)
        out.append((first, f"Cycle {c.n}, {_day_list(days)} logged: " + "; ".join(parts) + "."))
    return out


def effects_list(reg, effects, c, only=None, family=()):
    """The numbered side effects; ``only``: the cycles to list (the numbers stay those of the full list). ``family``:
    summaries of the family's symptom log, listed in date order and marked as such rather than numbered."""
    if not effects and not family:
        return '<p class="m">No side effects are recorded for this regimen.</p>'
    items = []
    for d, txt in family:
        items.append((d, f'<li><b>Family log, {e(common.fmt(d))}</b>: {e(txt)}</li>'))
    for i, (d, txt, who) in enumerate(effects):
        cy = reg.cycle_of(D(d))
        if only is not None and cy not in only:
            continue
        where = f"C{cy.n} day {cy.day(D(d))}" if cy else ""
        items.append((d, f'<li class="{"hl" if cy is c else ""}"><b>[{i + 1}] {e(common.fmt(d))}</b> ({e(where)}{", " + e(who) if who else ""}): {e(txt)}</li>'))
    return f'<ol class="se">{"".join(html for _, html in sorted(items, key=lambda t: t[0]))}</ol>'


def expected_list(reg):
    cur = reg.current()
    items = []
    if cur:
        for day, d, st, _ in cur.doses():
            if st == "expected":
                items.append(f"Cycle {cur.n} day {day}: {common.fmt(d.isoformat())}")
    nxt = (cur or reg.cycles[-1]).last + timedelta(days=1)
    if reg.ongoing:
        items.append(f"Cycle {(cur or reg.cycles[-1]).n + 1} day 1: {common.fmt(nxt.isoformat())}")
    for d, txt in reg.r.get("planned", []):
        items.append(f"{d}: {txt}")
    return "".join(f"<li>{e(t)}</li>" for t in items)


CSS = common.CSS + """
@page { size: Letter landscape; margin: 9mm 10mm 10mm; }
body, .viz-root { background: #fff; } .viz-root { padding: 0; font-size: 9pt; } .wrap { max-width: none; }
h1 { font-size: 15pt; margin: 0 0 1mm; } h2 { font-size: 11.5pt; margin: 2.5mm 0 1mm; border: 0; }
.sub { font-size: 8.4pt; color: var(--text-secondary); margin: 0 0 2mm; max-width: none; } .card { padding: 2mm 3mm; border-radius: 6px; }
.legend { font-size: 8pt; gap: 1mm 4mm; margin: 0 0 1.5mm; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5mm 4mm; } .m { color: var(--text-secondary); font-size: 8pt; }
section.p + section.p { break-before: page; }
.warn { border: 1px solid var(--series-4); background: #fff8e6; border-radius: 6px; padding: 1.5mm 3mm; font-size: 8.4pt; margin: 0 0 2mm; }
table.sum { font-size: 8pt; } table.sum td, table.sum th { padding: 1mm 2mm; } table.sum b { color: var(--series-2); }
ol.se { margin: 0; padding-left: 0; list-style: none; font-size: 7.8pt; columns: 2; column-gap: 6mm; } ol.se li { margin: 0 0 .6mm; break-inside: avoid; }
ol.se li.hl b { color: var(--text-primary); } ul.x { margin: 0; padding-left: 4mm; font-size: 8.4pt; }
.cols { display: grid; grid-template-columns: 1.2fr 1fr; gap: 4mm; } .card { break-inside: avoid; } h2.pb { break-before: page; }
"""


def build(r, data):
    reg = Regimen(r)
    c, cur = reg.latest_complete(), reg.current()
    if c is None:   # nothing completed yet: show the cycle in progress
        c, cur = cur, None
    effects = sorted([(str(d), t, "") for d, t in r.get("side_effects", [])] +
                     [(str(d), t, "family report") for d, t in r.get("symptom_log", [])])
    sched = f"days {', '.join(map(str, reg.days[:-1]))} and {reg.days[-1]}" if len(reg.days) > 1 else f"day {reg.days[0]}"
    now = (f"now cycle {cur.n}, day {(reg.today - cur.start).days + 1} ({common.fmt(C.today)})" if cur
           else f"{len(reg.cycles)} cycles, ended {common.fmt(reg.end.isoformat())}")
    sub = (f"{e(C.summary)} · prepared {C.built}. {e(reg.drug)} started {common.fmt(r['start'])}: {sched} of a {reg.length}-day cycle; "
           f"{now}. Cycle numbers count from the first dose. Lab values are read from the notes' lab results (visit-note tables and visit summaries); "
           f"{e(C['tumor_marker']['name'])} from the case's marker history.")
    warn = ""
    if reg.has_records and reg.records_from > reg.start:
        warn = (f'<div class="warn"><b>Infusion records start {common.fmt(reg.records_from.isoformat())}.</b> Doses before then are shown '
                'as "not confirmed" (?); from then on, a scheduled dose with no infusion record is shown as not given (✕).</div>')
    if not reg.has_records:
        warn = ('<div class="warn"><b>Doses not confirmed.</b> No infusion or administration records are in these records yet, so a '
                'scheduled dose is shown as "not confirmed" (?), not as given. Labs drawn on a dose day do not show that the dose was '
                'given. Add the infusion records (or the family\'s list of doses given and held) and rebuild.</div>')
    so_far = ('<span><svg width="22" height="8"><line x1="0" x2="22" y1="4" y2="4" stroke="var(--text-muted)" stroke-dasharray="2 3"/>'
              f'</svg> cycle {cur.n} so far</span>') if cur else ""
    legend = ('<div class="legend"><span>● given</span><span>✕ not given</span><span>? not confirmed</span><span>○ expected</span>'
              '<span><i class="sw" style="background:var(--series-1);opacity:.25"></i>typical normal range</span>'
              '<span><svg width="10" height="10"><circle cx="5" cy="5" r="3.2" fill="var(--series-2)"/></svg> outside the normal range '
              '(G1–G4 = CTCAE grade)</span><span><svg width="22" height="8"><line x1="0" x2="22" y1="4" y2="4" stroke="var(--series-4)" '
              f'stroke-dasharray="4 3"/></svg> grade line</span>'
              f'{so_far}'
              '<span>vertical lines = dose days</span></div>')
    panels = "".join(f'<div>{panel(reg, c, cur, keys, data)}</div>' for keys in PANELS + [["CA"]])
    p1 = (f'<section class="p"><h1>{e(reg.drug)}: cycle {c.n}, {common.fmt(c.start.isoformat())} – {common.fmt(c.last.isoformat())}'
          f'{" (latest completed cycle)" if cur else ""}</h1><p class="sub">{sub}</p>{warn}{legend}'
          f'<div class="card">{dose_strip(reg, c, cur, effects)}<div class="grid2">{panels}</div></div>'
          f'<h2>Side effects in cycles {c.n}{" and " + str(cur.n) if cur else ""} (numbered as on the dose rows; cycles '
          f'{reg.shown[0].n}–{reg.shown[-1].n} on the summary page)</h2>{effects_list(reg, effects, c, only=(c, cur))}</section>')
    overlays = "".join(f"<div>{overlay(reg, k, data)}</div>" for k in ("ANC", "WBC", "PLT", "HGB", "ALT", "RBC"))
    p2 = (f'<section class="p"><h2>{window_title(reg)}</h2>'
          '<p class="sub">Each row is one cycle, day by day: green = dose given, orange ✕ = not given, grey ? = not confirmed, dashed = '
          'expected; dots under a day = labs drawn; the outlined day is today.</p>'
          f'<div class="card">{calendar(reg, data)}</div>'
          f'<h2{" class=pb" if len(reg.shown) > 8 else ""}>The same tests, cycle over cycle</h2><p class="sub">Day of cycle on the axis, one line per cycle: whether the low point '
          'deepens, or recovery by the next day 1 slows, from one cycle to the next.</p>'
          f'<div class="card"><div class="grid2">{overlays}</div></div></section>')
    logged = family_log(reg)
    log_note = ("" if r.get("symptom_log") or logged else
                '<p class="m">No family symptom log yet. Visit notes record side effects only on visit days, so the days between '
                'doses, when counts are lowest, are mostly blank. Each build prints a log sheet for the cycle in progress '
                '(<code>symptom_log_…_cycleN</code>, PDF and spreadsheet); a filled-in spreadsheet put with the records is read like '
                'any other record, and its entries appear here as family reports.</p>')
    p3 = (f'<section class="p"><h2>Cycle summary</h2>{summary_table(reg, data, effects)}'
          f'<h2>Side effects, cycles {reg.shown[0].n}–{reg.shown[-1].n}</h2>'
          f'{effects_list(reg, effects, c, only=reg.shown, family=log_summaries(reg, logged))}'
          f'<div class="cols"><div><h2>Expected next</h2><ul class="x">{expected_list(reg)}</ul>{log_note}</div>'
          '<div><h2>How to read this</h2><ul class="x">'
          '<li>Grades are the Common Terminology Criteria for Adverse Events (CTCAE v5.0) cut-offs, shown for orientation; the care '
          'team decides what they mean for treatment. Liver grades assume a normal baseline.</li>'
          '<li>Normal ranges are typical adult values matched to the lab\'s own high/low flags; the lab\'s exact ranges may differ.</li>'
          '<li>Lab values come from visit-note lab tables (complete rows only, so a date is never guessed) and visit summaries. '
          'Neutrophil counts are missing where no differential was reported.</li>'
          '<li>A lab drawn up to 3 days before day 1 counts as that cycle\'s pre-dose value ("pre").</li>'
          f'<li>{"A dose is given only when an infusion record shows it." if reg.has_records else "Until infusion records are added, no dose is shown as given."}</li>'
          '</ul></div></div></section>')
    return reg, p1 + p2 + p3


def main():
    regs = [r for r in C.get("cycles", []) if r.get("report", True)]
    if not regs:
        print("skipped: cycles (no cycles: in the case)")
        return None
    data = lab_data()
    for r in regs:
        reg, body = build(r, data)
        slug = re.sub(r"[^a-z0-9]+", "_", reg.drug.lower()).strip("_")
        doc = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{e(reg.drug)} cycles</title><style>{CSS}</style></head>'
               f'<body><div class="viz-root print"><div class="wrap">{body}</div></div></body></html>')
        pdf = common.write_and_print(f"cycles_{slug}", doc, f"cycles_{slug}_{C.built}.pdf")
        print("built:", pdf.name, pdf.stat().st_size, "bytes;", len(reg.cycles), "cycles")
        if r.get("symptom_log_sheet", True):   # the family's log for the cycle in progress (symptom_log.py)
            from . import symptom_log
            for f in symptom_log.build(reg, slug):
                print("built:", f.name)


# --- discovery ----------------------------------------------------------------------------------------------------------
# Regimen statements as oncology notes print them. Plan lines name the days and the cycle ("Gemcitabine 1000 mg/m2 D1,8,15
# Q28D ... Start: C1D1 on 07/24/2026"); history lines the days and interval ("Gemcitabine [1000 mg/m2; day 1, 8, 15] q28 days:
# initiated 7/24/2026"); a plan line with no day list is one dose per cycle. Other EHRs: add patterns in the case (cycles_discovery: patterns), with the same group names.
DISCOVERY = [
    r"^(?P<drug>[A-Z][A-Za-z-]+(?: [A-Za-z-]+)?)\s+(?:\(?[\d.,]+\s*mg(?:/m2|/kg)?\)?\s+)?(?:(?P<days>D\d+(?:[,-]\d+)*)\s+)?Q(?P<len>\d+)D\b"
    r"[^\n]*?Start:\s*C1D1 on (?P<start>\d{1,2}/\d{1,2}/\d{4})",
    r"(?P<drug>[A-Z][A-Za-z-]+)\s*\[[^\]\n]*?days? (?P<days>\d+(?:,\s*\d+)*)\]\s*q(?P<len>\d+) days?:?\s*(?P<initiated>initiated) (?P<start>\d{1,2}/\d{1,2}/\d{4})",
]
INTERVAL = re.compile(r"\b(?:every (?P<w>\d|two|three|four) weeks|q(?P<q>\d)\s?w(?:ee)?ks?\b|every (?P<d>\d{2}) days)", re.I)
WORDS = {"two": 2, "three": 3, "four": 4}


def _days(s):
    if not s:   # a plan line with no day list ("Q21D"): one dose, on day 1
        return [1]
    s = s.lstrip("Dd")
    if "-" in s and "," not in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in re.split(r"[,\s]+", s) if x]


def _iso(mdy):
    m, d, y = map(int, mdy.split("/"))
    return date(y, m, d).isoformat()


def discover(log=print):
    """Propose regimens from the notes: drug, schedule, first day 1, the notes that say so, intervals the notes state
    elsewhere (to catch a mismatch), when it ended, lab draws that fall on the scheduled days, and infusion-record notes.

    The same drug started again within 120 days is one regimen (a plan rewritten before a delayed start); the history
    line's "initiated" date wins over a plan's C1D1. A regimen ends where a note says to discontinue it, or where the
    next regimen starts. Notes repeat old history lines, so a mention in a recent note does not make a regimen current."""
    pats = [re.compile(p, re.M) for p in C.get("cycles_discovery", {}).get("patterns", DISCOVERY)]
    notes = [f for f in sorted(C.notes.glob("*.md")) if re.match(r"\d{4}-\d{2}-\d{2}_", f.name)]
    hits = []   # (drug, start, length, days, initiated?, doc, note date, quote)
    texts = {}
    for f in notes:
        text = f.read_text(encoding="utf-8")
        doc, ndate = f.stem.rsplit("_", 1)[-1], f.stem.split("_", 1)[0]
        texts[doc] = (ndate, text, "infusion" in f.stem)
        for rx in pats:
            for m in rx.finditer(text):
                try:
                    start = _iso(m.group("start"))
                except ValueError:
                    continue
                name = re.sub(r"-[a-z]{4}\b", "", m.group("drug").strip())   # "deruxtecan-dlnk" -> "deruxtecan"
                hits.append((name[:1].upper() + name[1:].lower(), start, int(m.group("len")), tuple(_days(m.group("days"))),
                             bool(m.groupdict().get("initiated")), doc, ndate, m.group(0).splitlines()[0][:160]))
    regimens = []
    for h in sorted(hits, key=lambda h: (h[0], h[1])):
        first = h[0].split()[0]   # the same drug, written with or without its second name
        r = next((r for r in regimens if r["drug"].split()[0] == first and abs((D(h[1]) - D(r["starts"][-1])).days) <= 120), None)
        if r is None:
            r = {"drug": h[0], "starts": [], "initiated": None, "schedules": {}, "cited": []}
            regimens.append(r)
        if len(h[0]) > len(r["drug"]):
            r["drug"] = h[0]
        if h[1] not in r["starts"]:
            r["starts"].append(h[1])
        if h[4]:
            r["initiated"] = h[1]
        r["schedules"][(h[2], h[3])] = r["schedules"].get((h[2], h[3]), 0) + 1
        if len(r["cited"]) < 4 and all(c["doc"] != h[5] for c in r["cited"]):
            r["cited"].append({"doc": h[5], "quote": h[7]})
    for r in regimens:
        r["start"] = r["initiated"] or max(r["starts"])
    regimens.sort(key=lambda r: r["start"])
    lab_dates = {D(iso) for v in labs.parse({"WBC": [TESTS["WBC"][5], TESTS["WBC"][6]]})[0].values() for iso in v}
    out = []
    for i, r in enumerate(regimens):
        drug, start = r["drug"], r["start"]
        (length, days), _ = max(r["schedules"].items(), key=lambda kv: kv[1])
        key = drug.split()[0]
        stop = re.compile(rf"\bdiscontinu\w*\s+(?:the\s+)?{re.escape(key)}", re.I)
        stops = sorted(nd for nd, t, _ in texts.values() if nd > start and stop.search(t))
        nxt = next((x for x in regimens[i + 1:] if x["start"] > start and x["drug"].split()[0] != key), None)
        ends = [(stops[0], f"a note on {stops[0]} says to discontinue it")] if stops else []
        if nxt:
            ends.append((nxt["start"], f"{nxt['drug']} started {nxt['start']}"))
        end = min(ends) if ends else None
        until = D(end[0]) if end else D(C.today)
        sched_days, d0 = set(), D(start)
        while d0 <= until:
            sched_days |= {d0 + timedelta(days=d - 1) for d in days}
            d0 += timedelta(days=length)
        near = {d for d in lab_dates if D(start) - timedelta(days=BASELINE_DAYS) <= d <= until}
        on = {d for d in near if any(abs((d - x).days) <= 1 for x in sched_days)}
        intervals = {}
        for nd, t, _ in texts.values():
            if not (start <= nd <= until.isoformat()):
                continue
            for line in t.splitlines():
                if key.lower() in line.lower() and (m := INTERVAL.search(line)):
                    w = m.group("w") or m.group("q")
                    n = (int(w) if w.isdigit() else WORDS[w.lower()]) * 7 if w else int(m.group("d"))
                    if n and n != length:
                        intervals[n] = intervals.get(n, 0) + 1
        entry = {"drug": drug, "schedule": {"length": length, "days": list(days)}, "start": start,
                 "end": end[0] if end else "@today", "cited": r["cited"]}
        if end:
            entry["end_basis"] = end[1]
        if len(r["starts"]) > 1:
            entry["other_starts"] = [x for x in r["starts"] if x != start]
        if intervals:
            entry["check"] = "notes also state an interval of " + ", ".join(f"{n} days ({k}x)" for n, k in intervals.items())
        if near:
            entry["labs_on_schedule"] = f"{len(on)} of {len(near)} lab draws in this regimen fall on (or a day from) a scheduled dose day"
        inf = sorted(({"date": nd, "doc": doc} for doc, (nd, t, is_inf) in texts.items()
                      if is_inf and start <= nd <= until.isoformat() and key.lower() in t.lower()), key=lambda x: x["date"])
        if inf:   # ready to copy: each infusion note's date, and where the records start
            entry["infusions"] = inf
            if inf[0]["date"] > start:
                entry["infusion_records_from"] = inf[0]["date"]
        else:
            entry["infusion_records"] = "none found: doses show as not confirmed until infusions are listed"
        out.append(entry)
    f = C.dir / "cycles.suggested.yaml"
    f.write_text("# Proposed by `python -m reports cycles --discover`. Review before copying into the case under cycles:\n"
                 + yaml.safe_dump({"suggested_cycles": out}, allow_unicode=True, sort_keys=False, width=140), encoding="utf-8")
    log(f"cycles: {len(out)} regimen(s) found in {len(notes)} notes; wrote {f.name} (review before copying into the case)")
    return out
