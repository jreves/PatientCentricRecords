# The case file

The reports are drawn from a **case file**: a folder of YAML files describing one patient's course, plus an optional
narrative `document.html`. The default folder is `analysis/case/` (git-ignored); pass `--case DIR` or set `PCR_CASE`
to use another. [`examples/case/`](../examples/case/) is a complete, fictional case to copy from.

**Where the facts come from.** Write the case from the de-identified notes in `filtered/`, never from the raw records.
In practice you ask Claude Code to draft a section ("from `filtered/all_notes_chronological.md`, list every systemic
treatment with start and stop dates in `analysis/case/treatment.yaml`"), then check it line by line against what the
family knows. Mark uncertain dates as approximate rather than guessing.

## Conventions

- **Files merge in name order.** Top-level keys from later files are added; a top-level mapping that appears in two
  files is merged key by key. Split the case however you like (the example uses `case.yaml`, `treatment.yaml`,
  `charts.yaml` and `reports.yaml`).
- **Dates** are ISO (`2024-03-14`), quoted or not. Inside prose and table cells, write dates the way readers expect
  (`3/2024`).
- **`@today`** as a value means `dates.today`. Use it for anything ongoing, so the bars extend when you rebuild.
- **Color classes** (`cls`) name a color token from `reports/templates/base.css`: `--series-1` … `--series-6`.
- **HTML** is allowed only where noted (a few table cells and the emergency diagnosis line).
- **`texts:`** holds the prose fragments: page subtitles, footnotes. They can use `{built}`, `{today}`,
  `{records_through}` and `{summary}`.

## Common keys (`case.yaml` in the example)

```yaml
reports: [timelines, treatments, questions, emergency]   # optional: which reports to build (default: all)
notes_dir: ../../filtered/notes   # optional: the de-identified notes (default: the pipeline's filtered/notes)

dates:
  today: 2026-10-01           # the "today" line on the charts
  built: 2026-10-01           # printed on the reports and used in their file names
  records_through: 10/1/2026  # the latest record the case reflects (shown in the disclaimer)

patient:
  summary: "58, metastatic HR+/HER2− breast cancer"   # one line under each report title; no identifiers
  disclaimer: "Compiled by the family ... (through {records_through}) ..."   # printed at the foot of every page
  disclaimer_tail: "Patient identifiers removed; clinician names retained."    # appended, except on the emergency summary

tumor_marker:                 # the marker line under the timeline, and marker context in tooltips and tables
  name: CA 27-29
  unit: U/mL
  uln: 38.6                   # upper limit of normal (the dashed line)
  values: [[2021-03-10, 96], ...]
  # or read them from a published spreadsheet note:
  # source: {glob: "*_spreadsheet_*.md", pattern: '^\| (\d{4}-\d{2}-\d{2}) \| ([\d.]+) \|'}

texts: {note: "...", treatments_sub: "...", ...}
```

The disclaimer is required for any report you'll share. The wording the project uses:

> Compiled by the family with AI tools from her medical records (through {records_through}) and family reports.
> Informational use only; not for diagnosis or treatment decisions; may contain errors or omissions. Where it differs
> from provider records, the provider records are authoritative. Patient identifiers removed; clinician names retained.

## Treatments and events (`treatment.yaml`)

```yaml
therapy_groups:               # named groups of bars
  systemic:
    - {cls: endo, label: "Letrozole + palbociclib", start: 2021-03-15, end: 2023-06-01, note: "First line."}
    - {cls: adc, label: "Sacituzumab govitecan", start: 2025-10-06, end: "@today", ongoing: true, note: "..."}
  bone:
    - {cls: bone, label: Denosumab, start: 2021-03-15, end: "@today", ongoing: true,
       holds: [[2024-01-08, 2024-03-04, "Held for a dental extraction"]], note: "Monthly."}
systemic_group: systemic      # the group that answers "what was she on at the time?"
table_groups: [systemic, bone, radiation]

early_events: [...]           # same form as events; listed first
events:
  - {date: 2025-02-11, kind: hosp, stay: [2025-02-11, 2025-02-14], text: "Admitted for dehydration."}
operation_numbering: {kind: surgery, from: "2022"}   # optional: number operations from this date on

imaging:                      # [date, reading, finding]
  - [2023-05-22, tri-up, "CT: new liver lesions."]
adverse_events:               # [date, approximate?, event]
  - [2023-10-30, false, "Hyperglycemia (grade 3) on alpelisib."]
```

| Field | Meaning |
|---|---|
| bar `start` / `end` | ISO dates; `startApprox` / `endApprox: true` print a `~` |
| bar `ongoing` | draws an arrow at the right edge and "(ongoing)" in tables |
| bar `holds` | `[[from, to, why], ...]`, drawn dashed |
| bar `row` | stacks overlapping bars in one lane (0, 1, 2...) |
| event `kind` | `surgery`, `reduction` (closed reduction), `ed`, `hosp`, `proc` (procedure), `img` (work-up; not drawn) |
| imaging reading | `tri-up` progression / new disease, `tri-down` response, `circle-open` stable or other |

```yaml
implants:                     # every implanted device: what a surgeon needs before operating on short notice
  - {date: 2024-03-23, component: Femoral head, spec: "22.2 mm, +3 mm offset, V40 taper, CoCr",
     manufacturer: Stryker, catalog: 6260-9-222, status: current}
```

The table kind `implants` lists them, newest first. Copy manufacturer, model, size and catalog numbers exactly as the
operative note or implant log gives them. Serial and lot numbers identify the individual device and are removed by the
pipeline.

## Charts and pages (`charts.yaml`)

`charts:` defines each timeline by `type`:

- **`oncology`**: bars from `bar_groups` (`{group, lane}`), plus `extra_bars`; side effects in `ae_lane`; hospital
  events in `events_lane`; imaging in `imaging_lane`; `extra_markers` (`{lane, date, row, title, text}`); the tumor
  marker line underneath.
- **`hospital`**: events placed by `lane_of_kind` (`{surgery: ops, ed: ed, ...}`), stays in `stay_lane`, therapy
  groups for context through `bar_groups` (which can carry `row`, `faint`...).
- **`visits`**: a specialty course (eye care, cardiology...): explicit `bars`; `visits` as `[date, clinic, findings,
  procedure]`; `clinics` rules (`{prefix, shape}`); `procedure_lanes` (`{contains, lane, row}`) and
  `procedure_shapes` (`{contains, shape}`) place procedures named in a visit; `notes` (`[date, text]`) in `notes_lane`.

Every chart needs `id`, `aria` (a text description for screen readers), `ranges` (`name: [from, to]`),
`defaultRange`, `lanes` (`{id, label, h}`; optional `barH`, `labels: above`, `markerTop`), `cls`, and `legend` items:
`[sw, --series-n, label]` for a color swatch, `[held, "", ""]` for the held pattern, `[txt, symbol, label]`.
`guide_kinds` draws dashed vertical guides at events of those kinds.

`pages:` makes interactive HTML pages: `{chart, file, title, sub, ranges_ui: [[range, label]], tables: [{title,
kind}]}`. Table kinds: `therapies`, `adverse_events`, `events`, `imaging`, `stays`, `visits:<chart>`.

`chart_pdfs:` prints a chart page to PDF with every marker numbered and keyed: `{chart, range, name, title,
fig_title, sub, how, bars_title, tables: <page>}`; optional `extra: [{range, title, how, bars_title}]` adds more
ranges, and `skip: [lane ids]` leaves lanes out of the key.

`document:` (optional) builds the full timeline from your narrative: `{file: document.html, output: name, figures:
{FIG_NAME: {chart, range, id, legend}}}`. In `document.html`, `{{FIG_NAME}}` is replaced by the chart, and
`{{CSS}}`, `{{DOC_CSS}}`, `{{RENDERER}}`, `{{BUILT}}` by the engine's styles, renderer and build date.

`pack:` (optional, needs `document`) is a landscape chart pack: `{output, page_title, title, intro, sections: {brief,
left, right, lines: [start marker, end marker]}, figures: [{chart, range, title, how, bars_title, until}]}`. The
section markers are strings in `document.html` that bound each excerpt.

## Standalone reports (`reports.yaml`)

**`treatments_table`**: `title`; `phases: [[title, subtitle, rows]]`. A row is `[line, drug, dose, class,
prescriber, practice, start, stop, serious AEs, why stopped]`, and the last two may contain HTML. A drug starting
with `+` continues the regimen above it. `stop: ongoing` highlights the row. `radiation: [[site, dose, radiation
oncologist, practice, dates, serious AEs]]`.

**`questions`**: `disagree` and `gaps`, as `[topic, what the records show, question for the care team]`;
`settled: [[topic, resolution]]` and `settled_title`.

**`emergency`**:
- `fill_pdf: [[label, value]]` and `fill_docx: [[label, value, label, value]]`. An empty value leaves a blank to fill
  in. Name, date of birth, contacts and insurance are never in the published notes, so leave them blank.
- `diagnosis_html`, and `diagnosis_runs` (the same as Word runs, `[text, bold, half-point size or 0]`).
- `risks: [[title, text]]`, with the first `highlight` of them in the warning color.
- `extra_labs: [[test, value, date]]`, added after the latest blood counts found in the notes.
- `past`, `meds_note`, `meds_note_docx`, `meds: [[medicine, dose, for, prescriber]]`, `team: [[role, clinician,
  practice]]`, `vaccines: [[vaccine, date]]`, `vaccines_title`, `hospitals_label`, `hospitals`, `foot`, `creator`.

**`pathology`**:
- `tests: [{id, date, kind: tissue|blood|other, title, lab, summary, res: {MARKER: [status, text]}}]`, where status
  is `pos`, `neg`, `disc` (the records disagree) or `vus`.
- `untested: [[date, what, note]]`: progressions with no new test.
- `markers: [[MARKER, row label]]`, and `short: {MARKER: label}`.
- `treatments: [[name, class, start, end, basis, test id or null]]`, plus `classes: {class: [label, color]}` and
  `link_classes`.
- Optional: `axis: [[from, to]]` (or two segments to compress a quiet gap), `ticks`, `marker_gap_note`.
- Texts: `pathology_sub`, `pathology_tracks`, `pathology_mirror`, `pathology_note`, and optionally `pathology_alert`.

**`blood_counts`**: `title`, optional `start`/`end`, `doses: [[drug, class, [[start, end, label]], [[hold start, hold
end]]]]`, `events: [[date, text]]`, optional `panels: [[key, label, unit, low, high, [[threshold, note]]]]`. The values come from lab tables in the notes; `labs:` (`tests`,
`header`, `units_pattern`) adapts the parser to another lab format. Text: `blood_counts_sub`.

**`vitals`**: `title`, optional `start`/`end`, and `weight_axis: [low, high, [ticks]]`. Weight, Karnofsky/PPS and pain
are read from the notes. Text: `vitals_sub` with `{stats}`, `{reported}` and `{n_pps}`.

**`medications`**: `title`, optional `start`/`end`; `extra: [[name, group, start, end, ongoing, note]]` for medicines
not on the visit lists; `current: [names]` from the family's current list (it wins over the notes); optional
`canon_extra: [[name, group, line pattern]]`, `groups`, `colors` and `note_types`. Texts: `medications_sub` and
`medications_note`.

**`overview`**:
- `sites: [{n, site, group, x, y, first, how, course, status, bar}]` on a 300-wide body figure, where the viewer's left
  is the patient's right. `status` is `removed`, `treated` or `active`. `negative` lists what was looked
  for and not found.
- `lines: [[line, label, class, start, end, ongoing, [best date, best text] or null, why ended, prog|tox|now]]`, plus
  `lines_title`.
- Optional `usage_years: [from, to]` and `usage_adjust: [[year, metric, delta]]`; `usage_title`.
- Texts: `overview_sites`, `overview_lines`, `overview_usage`.

## Citations and the source audit (`citations.yaml`)

Before the reports go to a new physician, the family should be able to say where each statement comes from.
`citations.yaml`, beside the case files, gives the sources for every claim:

```yaml
event/2025-02-11/hosp:
  src:
    - {doc: ex00000002, quote: "Admitted 2/11/2025 with dehydration"}   # a published note id and a verbatim quote
imaging/2023-05-22:
  src: [{doc: ex00000003, quote: "new liver lesions"}]
  accept: {"1.4 cm": "size is in the report's table, which the extractor split"}   # a detail accepted by hand, with a reason
emergency/vaccine/Influenza:
  src: [{family: "the family, 9/2026"}]                              # something the records don't contain
```

The keys name the claims: `therapy/<group>/<label>/<start>`, `event/<date>/<kind>`, `imaging/<date>`, `ae/<date>`,
`treatments/<line>/<drug>`, `pathology/<test id>`, `emergency/risk/<title>`, `chart/<chart>/visit/<date>`,
`narrative/<first words>`, and so on. `python -m reports audit` lists every key, and `--suggest` writes
`citations.suggested.yaml`: for each unsourced claim, the notes that contain the most of its details, and the line
that holds them. Review those suggestions before copying them in.

`python -m reports audit` runs after every build (`build --no-audit` skips it). For each claim it checks that:
- the cited note exists and contains the quote, word for word (line breaks and spacing are ignored);
- every **detail** of the claim is in the cited notes: each date (in any common format; `~` dates to the month),
  amount with a unit (`125 mg`, `20 Gy`, `1.4 cm`, `85%`), drug or test name from `config/medical_terms.txt` (brand
  and generic names count as the same; add pairs under `audit: synonyms:`), and "Dr. X" surname;
- the **meaning** holds: the local model (Ollama, the pipeline's model or `audit: model:`) reads the claim with the
  cited passages and answers supported / partly / not supported. `--no-semantic` skips this; results are cached.

The appendix `source_audit_<built>.pdf` lists every claim with its status, its source notes and quotes, and what didn't
check out. The worklist comes first. The audit warns; it never stops a build.

When a report's section is missing, that report may fail to build. List only the reports you've written content for
in `reports:`.
