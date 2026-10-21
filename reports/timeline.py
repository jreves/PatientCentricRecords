"""Timeline charts and the documents built around them.

Three chart builders, each driven by a spec in the case file (``charts:``):
- ``oncology``: treatment lanes (bars from therapy groups, with tumour-marker context), side effects, hospital events,
  imaging milestones and the tumour-marker line;
- ``hospital``: operations, procedures, ED visits and stays, with treatment groups for context;
- ``visits``: a specialty course (e.g. eye care) with explicit bars, clinic visits, procedures placed by rules, and notes.

Then the interactive pages, the full timeline document (the case's narrative ``document.html`` with charts inserted),
the printable chart pack, and a PDF version of each chart page.
"""
import re
from datetime import timedelta

from . import common
from .common import D, e, fmt

KIND = {"surgery": ("diamond", "Surgery"), "reduction": ("diamond-open", "Closed reduction"), "ed": ("circle-open", "ED visit"),
        "hosp": ("square", "Hospital stay"), "proc": ("circle", "Procedure"), "img": ("circle-open", "Diagnostic work-up")}
READING = {"tri-up": "progression / new disease", "tri-down": "response", "circle-open": "stable / other"}


def C():
    return common.case()


# --- tumour marker context -------------------------------------------------------------------------------------------
def mname():
    return C()["tumor_marker"]["name"]


def uln():
    return C()["tumor_marker"]["uln"]


def ca_near(s, days):
    t = D(s); best = None
    for d, v in C().marker:
        gap = abs((D(d) - t).days)
        if gap <= days and (best is None or gap < best[2]):
            best = (d, v, gap)
    return best


def ca_before(s, days):
    t = D(s); best = None
    for d, v in C().marker:
        if D(d) <= t + timedelta(days=1) and (t - D(d)).days <= days:
            best = (d, v, 0)
    return best


def ca_span(start, end):
    a = ca_near(start, 45) or ca_before(start, 90); b = ca_before(end, 120)
    if not a:
        return ""
    if not b or b[0] == a[0]:
        return f"{mname()} at start: {a[1]:g} ({fmt(a[0])})"
    pct = round((b[1] - a[1]) / a[1] * 100)
    return f"{mname()}: {a[1]:g} ({fmt(a[0])}) → {b[1]:g} ({fmt(b[0])}), {'+' if pct >= 0 else ''}{pct}%"


def ca_point(s):
    p = ca_before(s, 120)
    if not p:
        return ""
    prior = ca_before((D(p[0]) - timedelta(days=90)).isoformat(), 120)
    trend = ""
    if prior and prior[0] != p[0]:
        d = p[1] - prior[1]
        trend = f", {'↑ +' if d > 0 else '↓ ' if d < 0 else '→ '}{d:.1f} vs {fmt(prior[0])}"
    return f"{mname()}: {p[1]:g} ({fmt(p[0])}){trend}{' · above normal' if p[1] > uln() else ''}"


def systemic():
    return C()["therapy_groups"][C().get("systemic_group", "systemic")]


def on_therapy(s):
    t = D(s); out = []
    for b in systemic():
        if D(b["start"]) <= t <= D(b["end"]) + timedelta(days=1):
            held = any(D(h[0]) <= t <= D(h[1]) for h in b.get("holds", []))
            out.append(b["label"] + (" (held)" if held else ""))
    return ", ".join(out) or "none (between lines)"


def with_ctx(bars):
    out = []
    for b in bars:
        b = dict(b)
        b["ctx"] = ca_span(b["start"], b["end"])
        if b.get("holds"):
            b["holdCtx"] = ca_span(b["holds"][0][0], b["holds"][0][1])
        out.append(b)
    return out


def ca_points():
    return [[d, v, on_therapy(d)] for d, v in C().marker]


def events():
    """Clinical and hospital events in display order: early (pre-metastatic) ones first."""
    return C().get("early_events", []) + C().get("events", [])


def op_number(e_):
    """Operations are numbered from the date given in ``operation_numbering`` (matching the narrative); others are unnumbered."""
    cfg = C().get("operation_numbering")
    if not cfg:
        return ""
    ops = [x["date"] for x in C().get("events", []) if x["kind"] == cfg["kind"] and x["date"] >= cfg["from"]]
    return str(ops.index(e_["date"]) + 1) if e_["kind"] == cfg["kind"] and e_["date"] in ops else ""


def guides(kinds):
    return [dict(date=x["date"]) for x in C().get("events", []) if x["kind"] in kinds]


# --- chart builders --------------------------------------------------------------------------------------------------
def build_oncology(spec):
    groups = C()["therapy_groups"]
    bars = []
    for g in spec["bar_groups"]:
        bars += [dict(b, lane=g["lane"]) for b in with_ctx(groups[g["group"]])]
    bars += [dict(b) for b in spec.get("extra_bars", [])]
    markers = []
    for d, approx, text in C().get("adverse_events", []):
        markers.append(dict(lane=spec["ae_lane"], date=d, shape="bang", approx=approx, title="Serious side effect", text=text, ctx=ca_point(d)))
    for m in spec.get("extra_markers", []):
        markers.append(dict(lane=m["lane"], date=m["date"], shape=m.get("shape", "bang"), row=m["row"], title=m["title"], text=m["text"],
                            ctx=ca_point(m["date"])))
    for ev in events():
        if ev["kind"] == "img":
            continue
        shape, kind = KIND[ev["kind"]]
        n = op_number(ev)
        markers.append(dict(lane=spec["events_lane"], date=ev["date"], shape=shape, label=n, title=f"{'Operation ' + n + ': ' if n else ''}{kind}",
                            text=ev["text"], ctx=f"On: {on_therapy(ev['date'])}" + (f" · {ca_point(ev['date'])}" if ca_point(ev["date"]) else "")))
    for d, shape, text in C().get("imaging", []):
        markers.append(dict(lane=spec["imaging_lane"], date=d, shape=shape, title="Imaging", text=text, ctx=ca_point(d)))
    m = C()["tumor_marker"]
    return dict(id=spec["id"], aria=spec["aria"], ranges=spec["ranges"], defaultRange=spec["defaultRange"], lanes=spec["lanes"], bars=bars,
                markers=markers, guides=guides(spec.get("guide_kinds", [])), today=C().today,
                line=dict(title=f"{m['name']} ({m['unit']})", label=m["name"], unit=m["unit"], uln=m["uln"], points=ca_points()), cls=spec["cls"])


def build_hospital(spec):
    bars, markers = [], []
    for ev in events():
        if ev["kind"] == "img":
            continue
        shape, kind = KIND[ev["kind"]]
        label = op_number(ev)
        markers.append(dict(lane=spec["lane_of_kind"][ev["kind"]], date=ev["date"], shape=shape, label=label,
                            title=f"{'Operation ' + label + ': ' if label else ''}{kind}", text=ev["text"], ctx=f"On: {on_therapy(ev['date'])}"))
        if ev.get("stay"):
            s0, s1 = ev["stay"]
            bars.append(dict(lane=spec["stay_lane"], cls="stay", label="", nolabel=True, start=s0, end=(D(s1) + timedelta(days=1)).isoformat(),
                             note=f"Hospital stay {fmt(s0)} – {fmt(s1)}: {ev['text']}"))
    groups = C()["therapy_groups"]
    for g in spec["bar_groups"]:
        extra = {k: v for k, v in g.items() if k not in ("group",)}
        bars += [dict(b, **extra) for b in groups[g["group"]]]
    return dict(id=spec["id"], aria=spec["aria"], labelWidth=spec["labelWidth"], ranges=spec["ranges"], defaultRange=spec["defaultRange"],
                lanes=spec["lanes"], bars=bars, markers=markers, guides=guides(spec.get("guide_kinds", [])), today=C().today, line=None, cls=spec["cls"])


def build_visits(spec):
    markers = []
    for d, clinic, finding, proc in spec["visits"]:
        rule = next((r for r in spec["clinics"] if clinic.startswith(r["prefix"])), {})
        markers.append(dict(lane=spec["visit_lane"], date=d, shape=rule.get("shape", "circle"), cls=None, title=clinic + rule.get("title_suffix", ""),
                            text=finding + (f" Procedure: {proc}." if proc else "")))
        for part in re.split(r" \+ ", proc):
            if not part:
                continue
            lr = next((r for r in spec["procedure_lanes"] if r["contains"] in part), None)
            if not lr:
                continue
            shape = next((r["shape"] for r in spec["procedure_shapes"] if r["contains"] in part.lower()), spec.get("procedure_shape", "diamond"))
            markers.append(dict(lane=lr["lane"], date=d, shape=shape, row=lr["row"], title=part, text=finding))
    for d, text in spec.get("notes", []):
        markers.append(dict(lane=spec["notes_lane"], date=d, shape="bang", title=spec["notes_title"], text=text))
    return dict(id=spec["id"], aria=spec["aria"], labelWidth=spec["labelWidth"], ranges=spec["ranges"], defaultRange=spec["defaultRange"],
                lanes=spec["lanes"], bars=spec["bars"], markers=markers, guides=spec.get("guides", []), today=C().today, line=None, cls=spec["cls"])


BUILDERS = {"oncology": build_oncology, "hospital": build_hospital, "visits": build_visits}


def charts():
    return {k: BUILDERS[s["type"]](s) for k, s in C()["charts"].items()}


def legend(key):
    return [tuple(x) for x in C()["charts"][key]["legend"]]


# --- tables ------------------------------------------------------------------------------------------------------------
def table_rows(kind):
    c, M = C(), mname()
    strip = lambda s: s.replace(f"{M}: ", "")
    if kind == "therapies":
        return [[f"{'~' if b.get('startApprox') else ''}{fmt(b['start'])} – {'~' if b.get('endApprox') else ''}{fmt(b['end'])}{' (ongoing)' if b.get('ongoing') else ''}",
                 b["label"], b["note"] + "".join(" " + h[2] + "." for h in b.get("holds", [])), strip(ca_span(b["start"], b["end"]))]
                for g in c["table_groups"] for b in c["therapy_groups"][g]]
    if kind == "adverse_events":
        return [[("~" if a else "") + fmt(d), t, strip(ca_point(d))] for d, a, t in c.get("adverse_events", [])]
    if kind == "events":
        return [[fmt(x["date"]), op_number(x), KIND[x["kind"]][1], x["text"], on_therapy(x["date"]), strip(ca_point(x["date"]))]
                for x in events() if x["kind"] != "img"]
    if kind == "imaging":
        return [[fmt(d), READING[s], t] for d, s, t in c.get("imaging", [])]
    if kind == "stays":
        return [[fmt(x["date"]), op_number(x), KIND[x["kind"]][1], x["text"], (f"{fmt(x['stay'][0])} – {fmt(x['stay'][1])}" if x.get("stay") else ""),
                 on_therapy(x["date"])] for x in events() if x["kind"] != "img"]
    if kind.startswith("visits:"):
        return [[fmt(d), cl, f, p] for d, cl, f, p in c["charts"][kind.split(":", 1)[1]]["visits"]]
    if kind == "implants":   # every implanted component, newest first: what a surgeon needs before operating
        # catalog numbers must never wrap mid-number: non-breaking hyphens in the display only
        return [[fmt(i["date"]), i["component"], i["spec"], i.get("manufacturer", ""), str(i.get("catalog", "")).replace("-", "‑"),
                 i.get("status", "")]
                for i in sorted(c.get("implants", []), key=lambda i: i["date"], reverse=True)]
    raise KeyError(kind)


HEADS = {"therapies": lambda M: ["Dates", "Treatment", "Notes", M], "adverse_events": lambda M: ["Date", "Event", M],
         "events": lambda M: ["Date", "#", "Kind", "Event", "Cancer therapy at the time", M], "imaging": lambda M: ["Date", "Reading", "Finding"],
         "stays": lambda M: ["Date", "Op", "Kind", "Event", "Stay", "Cancer therapy at the time"], "visits": lambda M: ["Date", "Clinic", "Findings", "Procedure"],
         "implants": lambda M: ["Implanted", "Component", "Specification", "Manufacturer", "Catalog no.", "Status"]}


def tables(page):
    return "".join(common.table(t["title"], HEADS[t["kind"].split(":")[0]](mname()), table_rows(t["kind"])) for t in page["tables"])


# --- outputs ----------------------------------------------------------------------------------------------------------
def build_pages(cfgs):
    c = C()
    for key, pg in c["pages"].items():
        body = common.chart_block(cfgs[pg["chart"]], [tuple(r) for r in pg["ranges_ui"]], legend(pg["chart"])) + tables(pg)
        (common.out_dir() / pg["file"]).write_text(common.page(pg["title"], pg["sub"], body, c.text("note")), encoding="utf-8")


def build_document(cfgs):
    c = C()
    doc = (c.dir / c["document"]["file"]).read_text(encoding="utf-8")
    figs = {}
    for ph, f in c["document"]["figures"].items():
        cfg = dict(cfgs[f["chart"]])
        if f.get("id"):
            cfg["id"] = f["id"]
        if f.get("range"):
            cfg["defaultRange"] = f["range"]
        figs["{{" + ph + "}}"] = common.chart_block(cfg, [], legend(f["chart"]) if f.get("legend", True) else [], width=f.get("width", 1100))
    figs.update({"{{CSS}}": common.CSS, "{{DOC_CSS}}": common.DOC_CSS, "{{RENDERER}}": common.RENDERER, "{{BUILT}}": c.built})
    for k, v in figs.items():
        doc = doc.replace(k, v)
    return common.write_and_print(c["document"]["output"] + "_full", doc, f"{c['document']['output']}_{c.built}.pdf"), doc


def build_pack(cfgs, doc_src):
    c = C()
    p = c["pack"]
    raw = (c.dir / c["document"]["file"]).read_text(encoding="utf-8")
    head_css = common.print_head_css()
    sec = {k: common.doc_section(raw, *v) for k, v in p["sections"].items()}
    figs = ""
    for f in p["figures"]:
        cfg = dict(cfgs[f["chart"]])
        if f.get("id"):
            cfg["id"] = f["id"]
        figs += common.annotated_fig(cfg, f["range"], f["title"], f["how"], legend(f["chart"]), f["bars_title"], skip=f.get("skip", ()), until=f.get("until"))
    body = (f"<h1>{e(p['title'])}</h1>"
            f'<p class="muted">{c.summary} · prepared {c.built} from the de-identified records. {p["intro"]}</p>'
            f"{sec['brief']}<div class=\"cols\"><div>{sec['left']}</div><div>{sec['right']}</div></div>"
            f'<section class="fig-page">{sec["lines"]}</section>' + figs + f'<p class="foot">{c.text("note")}</p>')
    html_doc = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{e(p["page_title"])}</title>'
                f"<style>{head_css}{common.PACK_CSS}</style></head><body><div class=\"viz-root print\"><div class=\"wrap\">"
                f"<script>{common.RENDERER}</script>{body}</div></div></body></html>")
    return common.write_and_print(p["output"], html_doc, f"{p['output']}_{c.built}.pdf")


def build_chart_pdfs(cfgs):
    c = C()
    for s in c.get("chart_pdfs", []):
        common.chart_pdf(cfgs[s["chart"]], s["range"], s["name"], s["title"], s["fig_title"], s["sub"], s["how"], legend(s["chart"]), s["bars_title"],
                         tables(c["pages"][s["tables"]]), c.text("note"), skip=s.get("skip", ()),
                         extra=[(x["range"], x["title"], x["how"], x["bars_title"]) for x in s.get("extra", [])])


def main():
    """The interactive pages always; the full document, chart pack and chart PDFs when the case defines them."""
    cfgs = charts()
    build_pages(cfgs)
    built = sorted(p["file"] for p in C()["pages"].values())
    if C().get("document"):
        pdf, doc = build_document(cfgs)
        built.append(pdf.name)
        if C().get("pack"):
            built.append(build_pack(cfgs, doc).name)
    build_chart_pdfs(cfgs)
    print("built:", ", ".join(built + [f"{s['name']} PDF" for s in C().get("chart_pdfs", [])]))
    return cfgs
