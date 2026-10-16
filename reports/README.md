# reports: the report engine

`python -m reports build [--case DIR] [--out DIR] [--notes DIR] [--only NAME ...]`

Builds reports from a **case file**: YAML facts about one patient, curated from the de-identified notes. It is
`analysis/case/` by default; see [docs/case-file.md](../docs/case-file.md) and the fictional
[examples/case](../examples/case/). The engine holds no patient facts. Everything specific to a patient (dates,
drugs, clinicians, prose) comes from the case file.

| Report (`--only`) | Module | Output |
|---|---|---|
| `timelines` | `timeline.py` | interactive chart pages (HTML), the full timeline document, a chart pack, and a PDF per chart |
| `treatments` | `treatments_table.py` | every cancer treatment by phase (landscape PDF) |
| `pathology` | `pathology.py` | biomarker and genomic results beside the treatments they informed |
| `blood_counts` | `blood_counts.py` + `labs.py` | WBC/ANC/hemoglobin/platelets from the notes' lab tables |
| `vitals` | `vitals.py` | weight, performance status and pain |
| `medications` | `medications.py` | every drug on the visit medication lists over time |
| `overview` | `overview.py` | body map of disease sites, treatment-line swimmer chart, hospital use |
| `questions` | `questions.py` | open questions and discrepancies for the care team |
| `emergency` | `emergency.py` + `emergency_docx.js` | two-page emergency/travel summary, PDF and editable Word |
| (after every build) | `audit.py` | the source audit: each statement in the case, its cited notes and quotes, checked locally |

Shared pieces: `case.py` (loading and merging the case YAML), `common.py` (page shells, the per-page disclaimer
footer, PDF printing), `renderer.js` (the swim-lane timeline renderer, inline SVG), `templates/` (CSS).

**PDF printing** uses a headless Chromium browser (Chrome, Edge or Chromium), found automatically per platform or set
with `PCR_BROWSER`. **The Word file** needs Node.js and `npm install` in this folder (it installs the `docx` package).

Every printed page carries the case's disclaimer (`patient.disclaimer`) and "report name · page X of Y".
