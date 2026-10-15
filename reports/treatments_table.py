"""A landscape table of every cancer treatment: drug, class, prescriber, practice, dates, serious adverse effects and why it
stopped, by phase, plus radiation. Rows come from the case file (``treatments_table:``)."""
import html

from . import common

e = html.escape
C = common.case()
T = C.get("treatments_table", {})

# phases: [title, subtitle, rows]; row: [line, drug, dose/schedule, class, prescriber, practice, start, stop, serious AEs (HTML), why stopped (HTML)].
# A row whose drug starts with "+" continues the regimen above it (same line).
PHASES = T.get("phases", [])
RADIATION = T.get("radiation", [])   # [site, dose, radiation oncologist, practice, dates, serious AEs]

CSS = common.CSS + """
@page { size: Letter landscape; margin: 9mm 9mm 10mm; }
body { background: #fff; } .viz-root { background: #fff; padding: 0; font-size: 8.6pt; }
.wrap { max-width: none; }
h1 { font-size: 15pt; margin: 0 0 1mm; } .sub { font-size: 8.3pt; color: var(--text-secondary); margin: 0 0 2.5mm; }
table.tx { width: 100%; border-collapse: collapse; font-size: 7.9pt; table-layout: fixed; background: #fff; }
table.tx th { font-size: 7.4pt; text-transform: uppercase; letter-spacing: .02em; color: var(--text-secondary); padding: 1.2mm 1.3mm;
  border-bottom: 1.5px solid var(--text-secondary); text-align: left; }
table.tx td { padding: 1.1mm 1.3mm; border-bottom: 1px solid var(--grid); vertical-align: top; line-height: 1.28; }
table.tx tr { break-inside: avoid; }
table.tx tr.phase td { background: #f1f0ec; font-weight: 700; font-size: 8.4pt; border-bottom: 1px solid var(--text-muted); padding-top: 1.6mm; }
table.tx tr.phase td span { font-weight: 400; color: var(--text-secondary); font-size: 7.7pt; margin-left: 2mm; }
table.tx tr.cont td { border-top: 0; } table.tx tr.first td { border-top: 1px solid var(--text-muted); }
td.line { font-weight: 700; } .dose { display: block; color: var(--text-secondary); font-size: 7.3pt; }
td.drug b { font-size: 8.3pt; } .current td { background: #f4f8fd; }
h2 { font-size: 10pt; margin: 3.5mm 0 1mm; border: 0; }
.foot { font-size: 7.3pt; color: var(--text-muted); margin-top: 2mm; line-height: 1.35; }
"""


def row_html(r, next_is_cont):
    line, drug, dose, cls, who, where, start, stop, ae, why = r
    cont = drug.startswith("+")
    classes = ["cont" if cont else "first"] + (["current"] if stop == "ongoing" else [])
    return (f'<tr class="{" ".join(classes)}"><td class="line">{e(line)}</td>'
            f'<td class="drug"><b>{e(drug)}</b>{f"<span class=dose>{e(dose)}</span>" if dose else ""}</td>'
            f"<td>{e(cls)}</td><td>{e(who)}</td><td>{e(where)}</td><td>{e(start)}</td><td>{e(stop)}</td><td>{ae}</td><td>{why}</td></tr>")


def main():
    cols = [("", "4%"), ("Drug", "15%"), ("Class", "12%"), ("Prescriber", "11%"), ("Practice", "10%"), ("Start", "7.5%"), ("Stop", "7.5%"),
            ("Serious adverse effects", "17%"), ("Why it stopped", "16%")]
    head = "".join(f'<th style="width:{w}">{e(c)}</th>' for c, w in cols)
    body = ""
    for title, sub, rows in PHASES:
        body += f'<tr class="phase"><td colspan="9">{e(title)}{f"<span>{e(sub)}</span>" if sub else ""}</td></tr>'
        for i, r in enumerate(rows):
            body += row_html(r, i + 1 < len(rows) and rows[i + 1][1].startswith("+"))
    rt = "".join(f"<tr><td><b>{e(a)}</b></td><td>{e(b)}</td><td>{e(c)}</td><td>{e(d)}</td><td>{e(f)}</td><td>{e(g)}</td></tr>"
                 for a, b, c, d, f, g in RADIATION)
    doc = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Cancer treatments</title><style>{CSS}</style></head>'
           f'<body><div class="viz-root"><div class="wrap">'
           f"<h1>{e(T['title'])}</h1>"
           f'<p class="sub">{C.text("treatments_sub")}</p>'
           f'<table class="tx"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
           f'<h2>Radiation</h2><table class="tx"><thead><tr><th style="width:24%">Site</th><th style="width:14%">Dose</th>'
           f'<th style="width:20%">Radiation oncologist</th><th style="width:16%">Practice</th><th style="width:12%">Dates</th>'
           f'<th style="width:14%">Serious adverse effects</th></tr></thead><tbody>{rt}</tbody></table>'
           f'<p class="foot">{C.text("treatments_foot")}</p>'
           "</div></div></body></html>")
    pdf = common.write_and_print("cancer_treatments", doc, f"cancer_treatments_{C.built}.pdf")
    print("built:", pdf.name, pdf.stat().st_size, "bytes")
    return pdf


if __name__ == "__main__":
    main()
