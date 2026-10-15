"""Emergency / travel medical summary (Letter portrait, 2 pages) for an unfamiliar ED or clinic, as a PDF and an editable Word
file. Content comes from the case file (``emergency:``); the latest blood counts come from the lab tables. Identity, contacts,
insurance and code status are left blank for the family to fill in: they are not in the published data by design."""
import html
import json
import pathlib
import shutil
import subprocess

from . import common, labs

e = html.escape
C = common.case()
EM = C.get("emergency", {})
RISKS = [tuple(x) for x in EM.get("risks", [])]
MEDS = [tuple(x) for x in EM.get("meds", [])]           # (medicine, dose / how, for, prescriber)
TEAM = [tuple(x) for x in EM.get("team", [])]           # (role, clinician, practice)
VACCINES = [tuple(x) for x in EM.get("vaccines", [])]   # (vaccine, date)
HOSPITALS = EM.get("hospitals", "")

CSS = common.CSS + """
@page { size: Letter; margin: 9mm 10mm 9mm; }
body, .viz-root { background: #fff; } .viz-root { padding: 0; font-size: 8.8pt; line-height: 1.3; } .wrap { max-width: none; }
h1 { font-size: 15pt; margin: 0; } h2 { font-size: 10pt; margin: 3mm 0 1mm; border-bottom: 1px solid var(--grid); padding-bottom: .6mm; }
.top { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 2.5px solid var(--text-primary); padding-bottom: 1mm; }
.top .when { font-size: 8pt; color: var(--text-secondary); }
.fill { display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 1.5mm 5mm; margin: 2mm 0; }
.fill div { border-bottom: 1px solid var(--text-secondary); padding-top: 4.5mm; font-size: 7.4pt; color: var(--text-secondary); }
.fill div.known { color: var(--text-primary); font-size: 8.4pt; }
.dx { background: #f4f3ef; border-radius: 5px; padding: 2mm 3mm; margin: 2mm 0; }
.dx b { font-size: 9.6pt; }
.risk { display: grid; grid-template-columns: 44mm 1fr; gap: 0 3mm; border-bottom: 1px solid var(--grid); padding: 1mm 0; break-inside: avoid; }
.risk .t { font-weight: 700; } .risk.hot .t { color: var(--series-2); }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }
table { font-size: 8pt; } th, td { padding: .8mm 1.5mm; } .phone { width: 30mm; border-bottom: 1px solid var(--text-secondary); }
.p2 { break-before: page; } .foot { font-size: 7.2pt; color: var(--text-muted); margin-top: 2mm; }
.labs td, .labs th { text-align: right; } .labs td:first-child, .labs th:first-child { text-align: left; }
"""


def lab_rows():
    """Latest blood counts from the lab tables, then the case's extra rows (tumour marker, weight...)."""
    data, _ = labs.parse()
    rows = []
    if data.get("WBC"):   # the counts drawn with the latest white count; neutrophils from their own latest date
        d = max(data["WBC"])
        anc_d = max(data["ANC"]) if data.get("ANC") else None
        for key, label, unit, when in (("WBC", "White blood cells", "×10³/µL", d), ("ANC", "Neutrophils (ANC)", "×10³/µL", anc_d),
                                       ("HGB", "Hemoglobin", "g/dL", d), ("PLT", "Platelets", "×10³/µL", d)):
            if when in data.get(key, {}):
                rows.append([label, f"{data[key][when]:g} {unit}", common.fmt(when)])
    return rows + [list(r) for r in EM.get("extra_labs", [])]


def main():
    rows = lab_rows()
    hot = EM.get("highlight", 2)
    risks = "".join(f'<div class="risk{" hot" if i < hot else ""}"><div class="t">{e(t)}</div><div>{e(x)}</div></div>' for i, (t, x) in enumerate(RISKS))
    meds = "".join(f"<tr><td><b>{e(m)}</b></td><td>{e(dose)}</td><td>{e(f)}</td><td class=\"muted\">{e(src)}</td></tr>" for m, dose, f, src in MEDS)
    vacc = "".join(f"<tr><td><b>{e(v)}</b></td><td>{e(d_)}</td></tr>" for v, d_ in VACCINES)
    team = "".join(f'<tr><td>{e(r)}</td><td><b>{e(n)}</b></td><td>{e(p)}</td><td class="phone"></td></tr>' for r, n, p in TEAM)
    fill = "".join(f'<div class="known">{v}</div>' if v else f"<div>{e(lab)}</div>" for lab, v in EM["fill_pdf"])
    labs_html = "".join(f"<tr><td>{e(a)}</td><td>{e(b)}</td><td>{e(c)}</td></tr>" for a, b, c in rows)
    body = f"""
<div class="top"><h1>Medical summary for emergencies and travel</h1><span class="when">{C.text("emergency_when")}</span></div>
<div class="fill">{fill}</div>
<div class="dx">{EM["diagnosis_html"]}</div>
<h2>Important for emergency care</h2>{risks}
<div class="two"><div><h2>Latest values</h2><table class="labs"><thead><tr><th></th><th>value</th><th>date</th></tr></thead><tbody>
{labs_html}</tbody></table></div>
<div><h2>Past cancer treatment (short)</h2><p style="margin:0">{e(EM["past"])}</p></div></div>
<section class="p2"><h2>Current medicines</h2><p class="muted" style="margin:0 0 1mm">{e(EM["meds_note"])}</p>
<table><thead><tr><th>Medicine</th><th>Dose / how</th><th>For</th><th>Prescriber</th></tr></thead><tbody>{meds}</tbody></table>
<h2>Care team</h2><table><thead><tr><th>Role</th><th>Clinician</th><th>Practice</th><th>Phone</th></tr></thead><tbody>{team}</tbody></table>
""" + (f"""<h2>{e(EM["vaccines_title"])}</h2><table><thead><tr><th>Vaccine</th><th>Date</th></tr></thead><tbody>{vacc}</tbody></table>
""" if VACCINES else "") + f"""<p style="margin:1.5mm 0 0"><b>{e(EM["hospitals_label"])}</b> {e(HOSPITALS)}</p>
<p class="foot">{e(EM["foot"])}</p></section>"""
    doc = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Emergency medical summary</title><style>{CSS}</style></head>'
           f'<body><div class="viz-root"><div class="wrap">{body}</div></div></body></html>')
    pdf = common.write_and_print("emergency_card", doc, f"emergency_summary_{C.built}.pdf", disclaimer=C.disclaimer)
    print("built:", pdf.name, pdf.stat().st_size, "bytes")
    write_docx(rows)
    return pdf


def write_docx(rows):
    """Editable Word version (emergency_docx.js with the docx package); same content, with fill-in cells."""
    data = {
        "built": C.built, "disclaimer": C.disclaimer, "subtitle": C.text("emergency_docx_subtitle"), "fill": EM["fill_docx"],
        "dx_runs": EM["diagnosis_runs"], "risks": RISKS, "hot": EM.get("highlight", 2), "labs": rows, "past": EM["past"],
        "meds_note": EM["meds_note_docx"], "meds": MEDS, "team": TEAM, "vaccines": VACCINES, "vaccines_title": EM.get("vaccines_title", ""),
        "hospitals_label": EM["hospitals_label"], "hospitals": HOSPITALS, "foot": EM["foot"], "creator": EM.get("creator", "Family"),
        "out": str(common.out_dir() / f"emergency_summary_{C.built}.docx"),
    }
    src = common.work_dir() / "emergency_card.json"
    src.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if not shutil.which("node") or not (common.HERE / "node_modules" / "docx").exists():
        print("skipped emergency_summary .docx (needs Node.js and `npm install` in reports/)")
        return
    subprocess.run(["node", str(common.HERE / "emergency_docx.js"), str(src)], check=True, cwd=common.HERE)
    print("built:", pathlib.Path(data["out"]).name)
