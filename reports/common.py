"""Shared report machinery: paths, styles, chart blocks, page shells, per-page disclaimer footers and PDF printing."""
import html
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import time
from datetime import date

from . import case as case_mod

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
CSS = (TEMPLATES / "base.css").read_text(encoding="utf-8")
DOC_CSS = (TEMPLATES / "document.css").read_text(encoding="utf-8")
PACK_CSS = (TEMPLATES / "pack.css").read_text(encoding="utf-8")
RENDERER = (HERE / "renderer.js").read_text(encoding="utf-8")
e = html.escape


def case():
    return case_mod.load()


def out_dir():
    """Finished reports go here (default analysis/, git-ignored); intermediate HTML in analysis/.work/."""
    d = pathlib.Path(os.environ.get("PCR_OUT") or case_mod.ROOT / "analysis").resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def work_dir():
    d = out_dir() / ".work"
    d.mkdir(exist_ok=True)
    return d


def D(s):
    return date.fromisoformat(s)


def fmt(s):
    d = D(s)
    return f"{d.month}/{d.day}/{d.year}"


def year_end(iso):
    """31 December of the year of an ISO date (the default right edge of a time axis)."""
    return date(D(iso).year, 12, 31)


def month_start(iso):
    d = D(iso)
    return date(d.year, d.month, 1)


def legend_html(items):
    out = []
    for kind, a, b in items:
        if kind == "sw":
            out.append(f'<span><i class="sw" style="background:var({a})"></i>{e(b)}</span>')
        elif kind == "held":
            out.append('<span><i class="sw" style="border:1.5px dashed var(--text-secondary)"></i>treatment held</span>')
        else:
            out.append(f"<span>{e(a)} {e(b)}</span>")
    return '<div class="legend" aria-hidden="true">' + "".join(out) + "</div>"


def table(title, head, rows):
    h = "".join(f"<th>{e(c)}</th>" for c in head)
    body = "".join("<tr>" + "".join(f'<td class="n">{e(c)}</td>' if i < 1 else f"<td>{e(c)}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f"<h2>{e(title)}</h2><table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>"


def chart_block(cfg, ranges_ui, legend, width=None):
    buttons = "".join(f'<button type="button" data-range="{k}" aria-pressed="{str(k == cfg["defaultRange"]).lower()}">{e(v)}</button>' for k, v in ranges_ui)
    ctrl = f'<div class="seg" role="group" aria-label="Time range">{buttons}</div>' if width is None else ""
    return (f'<div class="card" data-chart="{cfg["id"]}"><div class="controls">{ctrl}{legend_html(legend)}</div>'
            f'<div class="chart" id="host-{cfg["id"]}"></div></div>'
            f'<script>Timeline.mount({json.dumps(cfg)}, "host-{cfg["id"]}", {json.dumps({"width": width} if width else {})});</script>')


def page(title, sub, body, note, print_mode=False):
    """An interactive HTML page (charts with hover), ending with the disclaimer."""
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{e(title)}</title><style>{CSS}</style></head><body><div class=\"viz-root{' print' if print_mode else ''}\"><div class=\"wrap\">"
            f"<script>{RENDERER}</script><h1>{e(title)}</h1><p class=\"sub\">{sub}</p>{body}<p class=\"note\">{note}</p>"
            f'<p class="note" style="border-top:1px solid var(--grid);padding-top:8px;font-size:11px">{e(case().disclaimer_full)}</p></div></div></body></html>')


def footer_css(title, disclaimer):
    """Every printed page: the disclaimer bottom left, the report name and page number bottom right (CSS page-margin boxes)."""
    q = lambda t: '"' + t.replace("\\", "\\\\").replace('"', '\\"') + '"'
    box = "font-family: system-ui, 'Segoe UI', sans-serif; font-size: 6.3pt; color: #707070; vertical-align: top; padding-top: 2.2mm;"
    return (f"@page {{ margin-bottom: 15mm; @bottom-left {{ content: {q(disclaimer)}; {box} width: 70%; }} "
            f"@bottom-right {{ content: {q(title + ' · page ')} counter(page) \" of \" counter(pages); {box} text-align: right; white-space: nowrap; }} }}")


BROWSERS = {   # Chromium-family browsers that can print to PDF headlessly, in order of preference per platform
    "Windows": [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
    "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
               "/Applications/Chromium.app/Contents/MacOS/Chromium"],
    "Linux": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "msedge"],
}


def find_browser():
    """A headless-capable Chromium browser: $PCR_BROWSER, else the first one found for this platform (None if none)."""
    if os.environ.get("PCR_BROWSER"):
        return os.environ["PCR_BROWSER"]
    for c in BROWSERS.get(platform.system(), BROWSERS["Linux"]):
        p = c if os.path.isabs(c) else shutil.which(c)
        if p and os.path.exists(p):
            return p
    return None


def print_pdf(src_html, pdf, disclaimer=None):
    """Print an HTML file to PDF with a headless Chromium browser, adding the per-page disclaimer footer."""
    html_doc = src_html.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", html_doc, re.S)
    title = html.unescape(title.group(1)).strip() if title else pdf.stem
    html_doc = html_doc.replace("</head>", f"<style>{footer_css(title, disclaimer or case().disclaimer_full)}</style></head>", 1)
    src_html = src_html.with_name("_print_" + src_html.name)
    src_html.write_text(html_doc, encoding="utf-8")
    browser = find_browser()
    if not browser:
        raise SystemExit("No Chrome, Chromium or Edge found to print PDFs; install one or set PCR_BROWSER (see `python -m pipeline doctor`).")
    tmp = work_dir() / "printing.pdf"
    tmp.unlink(missing_ok=True)
    # A separate profile, or a headless browser hands the job to an already-running window and prints nothing.
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={work_dir() / '.browser-profile'}",
                    "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=15000", f"--print-to-pdf={tmp}", src_html.as_uri()], check=True, capture_output=True, timeout=180)
    # The browser can return before the file is written: wait until it exists and its size stops changing.
    last, deadline = -1, time.time() + 180
    while time.time() < deadline:
        size = tmp.stat().st_size if tmp.exists() else -1
        if size > 0 and size == last:
            break
        last = size
        time.sleep(2)
    else:
        raise SystemExit("PDF was not written")
    tmp.replace(pdf)


def write_and_print(name, html_doc, pdf_name, disclaimer=None):
    out = work_dir() / f"{name}.html"
    out.write_text(html_doc, encoding="utf-8")
    pdf = out_dir() / pdf_name
    print_pdf(out, pdf, disclaimer)
    return pdf


def doc_section(doc, start, end):
    i = doc.index(start)
    j = doc.index(end, i + len(start)) if end else len(doc)
    # Without the main document's figures (placeholder + caption), which the pack draws differently.
    return re.sub(r'<div class="fig[^"]*">\{\{FIG_\w+\}\}<div class="cap">.*?</div></div>', "", doc[i:j], flags=re.S)


def print_head_css():
    return (CSS + "\n" + DOC_CSS).replace("@page { size: Letter;", "@page { size: Letter landscape;")


def annotated_fig(cfg, rng, title, how, legend, bars_title, skip=(), until=None):
    """A static chart for print: every marker numbered, with a key (and a table of the bars) beneath it."""
    cid = f"p-{cfg['id']}"
    c = dict(cfg, id=cid, defaultRange=rng)
    opts = {"width": 1320, "annotate": {"range": rng, "barsTitle": bars_title, "skipLanes": list(skip), "until": until}, "keyHost": f"key-{cid}"}
    return (f'<section class="fig-page"><div class="fig-head"><h2>{e(title)}</h2><div class="how">{how}</div></div>'
            f'<div class="card" data-chart="{cid}"><div class="controls">{legend_html(legend)}</div><div class="chart" id="host-{cid}"></div></div>'
            f'<div id="key-{cid}"></div>'
            f'<script>Timeline.mount({json.dumps(c)}, "host-{cid}", {json.dumps(opts)});</script></section>')


def chart_pdf(cfg, rng, name, title, fig_title, sub, how, legend, bars_title, tables, note, skip=(), extra=()):
    """PDF version of an interactive chart page: the chart with every event numbered and its key, then the page's tables."""
    c = case()
    body = (f"<h1>{e(title)}</h1>"
            f'<p class="muted">{c.summary} · prepared {c.built} from the de-identified records. {sub}</p>'
            + '<div class="first-fig">' + annotated_fig(dict(cfg, id=f"{cfg['id']}-print"), rng, fig_title, how, legend, bars_title, skip=skip) + "</div>"
            + "".join(annotated_fig(dict(cfg, id=f"{cfg['id']}-print-{r}"), r, t, h, legend, bt, skip=skip) for r, t, h, bt in extra)
            + f'<section class="fig-page">{tables}</section><p class="foot">{note}</p>')
    html_doc = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{e(title)}</title>'
                f"<style>{print_head_css()}{PACK_CSS} .print .first-fig > .fig-page {{ break-before: auto; }} .print .first-fig .chart svg {{ max-height: 125mm !important; width: auto !important; max-width: 100%; display: block; margin: 0 auto; }} .print .first-fig .card {{ break-inside: auto; }}</style></head>"
                f"<body><div class=\"viz-root print\"><div class=\"wrap\"><script>{RENDERER}</script>{body}</div></div></body></html>")
    return write_and_print(f"{name}_print", html_doc, f"{name}_{c.built}.pdf")
