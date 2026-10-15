"""Open questions and discrepancies: where the records disagree, what they don't contain, and what has already been settled.
Items come from the case file (``questions:``): each is [topic, what the records show, question for the care team]."""
import html

from . import common

e = html.escape
C = common.case()
Q = C.get("questions", {})
DISAGREE = [tuple(x) for x in Q.get("disagree", [])]
GAPS = [tuple(x) for x in Q.get("gaps", [])]
SETTLED = [tuple(x) for x in Q.get("settled", [])]

CSS = common.CSS + """
@page { size: Letter; margin: 10mm 11mm 10mm; }
body, .viz-root { background: #fff; } .viz-root { padding: 0; font-size: 8.8pt; line-height: 1.3; } .wrap { max-width: none; }
h1 { font-size: 15pt; margin: 0 0 1mm; } h2 { font-size: 11pt; margin: 4mm 0 1.2mm; border-bottom: 1px solid var(--grid); padding-bottom: .6mm; }
.sub { font-size: 8.2pt; color: var(--text-secondary); margin: 0 0 1mm; }
table { font-size: 8pt; width: 100%; } th, td { padding: 1mm 1.6mm; vertical-align: top; } tr { break-inside: avoid; }
td.num { font-weight: 700; width: 5mm; } td.topic { font-weight: 700; width: 38mm; } td.q { width: 52mm; color: var(--text-primary); }
th { font-size: 7.4pt; text-transform: uppercase; letter-spacing: .03em; }
.check { display: inline-block; width: 3mm; height: 3mm; border: 1px solid var(--text-secondary); margin-right: 1.5mm; vertical-align: -0.5mm; }
"""


def rows(items, start):
    return "".join(f'<tr><td class="num">{i}</td><td class="topic">{e(t)}</td><td>{e(w)}</td><td class="q"><span class="check"></span>{e(q)}</td></tr>'
                   for i, (t, w, q) in enumerate(items, start))


def main():
    head = "<thead><tr><th>#</th><th>Topic</th><th>What the records show</th><th>Question for the care team</th></tr></thead>"
    settled = "".join(f"<tr><td class=\"topic\">{e(t)}</td><td>{e(w)}</td></tr>" for t, w in SETTLED)
    body = (f"<h1>Open questions and discrepancies</h1>"
            f'<p class="sub">{C.text("questions_sub")}</p>'
            f"<h2>A. Where the records disagree</h2><table>{head}<tbody>{rows(DISAGREE, 1)}</tbody></table>"
            f"<h2>B. Not in the records</h2><table>{head}<tbody>{rows(GAPS, len(DISAGREE) + 1)}</tbody></table>"
            + (f'<h2>{e(Q.get("settled_title", "C. Already settled"))}</h2><p class="sub">{C.text("questions_settled")}</p>'
               f"<table><tbody>{settled}</tbody></table>" if SETTLED else ""))
    doc = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Open questions and discrepancies</title><style>{CSS}</style></head>'
           f'<body><div class="viz-root"><div class="wrap">{body}</div></div></body></html>')
    pdf = common.write_and_print("questions", doc, f"open_questions_{C.built}.pdf")
    print("built:", pdf.name, pdf.stat().st_size, "bytes")
    return pdf


if __name__ == "__main__":
    main()
