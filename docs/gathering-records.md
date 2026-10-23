# Gathering records: what's worth downloading

Patient portals hold a lot of paper, and much of it adds nothing to a timeline. This guide is about finding the
records that do: the ones that say **what was done, when, by whom, at what dose, and with what result**. In short:

- **Get the clinicians' notes, not the visit summaries.**
- **Get the reports, not just the results.**
- **Get the complete record of each hospital stay.**
- **Get anything that lists medicines, doses or implants, with its date.**

## How detailed is useful

The reports are built from facts that can each be traced to a quote in a record. A record is valuable when it holds
those facts in writing:

| Useful | Less useful |
|---|---|
| The doctor's full note for a visit (history, exam, results, assessment and plan) | The after-visit summary handed to the patient (follow-up instructions, a medicine list) |
| The radiologist's report of a scan, with findings and impression | The scan images themselves, or a "result available" message |
| The pathology report, with receptor and biomarker results | A note that says "pathology reviewed" |
| A treatment plan or infusion record with drug, dose, schedule and cycle dates | An appointment list |
| An operative note naming the procedure, the findings and the implants used | A discharge instruction sheet |
| A lab table with values, units and dates | A single "normal" flag |

**Exact dates matter most.** The order of events is the whole point of a timeline, so a record that dates each event
("started 5/12/2021", "dose reduced to 80% on 6/3") is worth more than one that says "last spring".

**Detail matters where a later decision depends on it:** dose and schedule (and every change to them), why a treatment
stopped, test values with units, scan findings with sizes and sites. For surgery that also means the implant
manufacturer, model, size and catalog number, which a surgeon may need at short notice.

**More is fine.** Notes often repeat each other: an oncology note may carry the whole treatment history forward at
every visit. That's useful, because it gives several sources for each fact. Exact duplicates are recognized and
skipped, so re-downloading costs nothing. When notes disagree, the reports turn the disagreement into an open
question for the care team.

## The records to look for

### Clinic visits (the backbone)

- **Progress notes or clinical notes** from each specialist, especially the treating oncologist. In many portals
  these are under "Notes", "Clinical notes", "Visit notes" or "Open notes", separate from the visit summary.
- **Oncology notes are usually the richest source.** Many carry a running "oncology history" or "treatment history"
  with every past treatment and its dates, plus that visit's labs, vital signs, medicine list and plan.
- **Notes from other specialists:** surgery, radiation oncology, palliative care, eye care, infectious diseases,
  cardiology. Their complications and treatments run alongside the cancer care.

### Treatment records

- **Treatment plans or regimen pages:** drug, dose (for example mg/m²), days given, cycle length, start date. They
  are often a separate page or section in an oncology portal.
- **Infusion or medication administration records:** what was actually given and when, including holds and dose
  reductions. The chemotherapy cycles report counts a dose as given only when one of these shows it. Some portals put
  them in each visit summary's "Administered medications" section, so download the summary for every infusion day.
- **Radiation treatment summaries:** site, total dose, number of fractions, and dates.
- **Prescription histories** from pharmacy portals, for oral cancer drugs and supportive medicines.

### Tests and imaging

- **Pathology reports:** biopsy and surgical specimens, with tumour type, grade, and receptor results (ER, PR, HER2)
  or other biomarkers. Get each one, not just the first diagnosis. The biology can change over time.
- **Genetic and tumour-DNA reports** (inherited panels, tumour sequencing, blood-based tumour DNA tests). Get the full
  report with variant names, not a summary line.
- **Imaging reports** (CT, PET, MRI, bone scans, X-rays, ultrasounds, DXA): the written report, with findings and
  impression. A radiologist's comparison with earlier scans is especially useful.
- **Lab results over time:** blood counts, chemistry, and tumour markers. A portal's "trend" or "export to
  spreadsheet" view is ideal; lab tables inside visit notes work too.

### Hospital stays and emergencies

For each stay or ED visit, the most useful documents are:
- **The discharge summary:** why the patient came in, what was done, the diagnoses, and the medicines at discharge.
- **The history and physical (H&P)** and the **ED provider note**.
- **Operative notes and procedure notes**, and the **implant log** if one is in the surgical record.
- **Consult notes** from specialists seen during the stay.

Many hospital portals offer a **"download my record" or "View, Download, Transmit"** export, which gives C-CDA XML,
or a **full encounter summary** PDF. Both are complete and read accurately. The full encounter summary can run to
hundreds of pages, and that's fine: the pipeline splits it into sections and keeps the clinical ones.

### Medicines, allergies and vaccines

- **The family's own current medication list**, kept up to date and dated ("Updated 3/14/2025"). Provider medicine
  lists often keep medicines that were stopped long ago. The patient's own list answers "what is the patient actually taking
  now?", and the reports treat it as the authority for current medicines as of its date.
- **Allergy lists** from any recent record.
- **Vaccination histories** from pharmacy portals and the state immunization registry.

### Older records

Records from before the current portals often matter most for the early history: the first diagnosis, the first
surgery and pathology, the early treatments. Ask each hospital's or clinic's **medical records department (health
information management)** for:
- the **complete medical record** for a date range, or specifically
- **operative reports, pathology reports, discharge summaries, oncology consult notes, chemotherapy and radiation
  treatment summaries, and imaging reports**.

They often arrive as scanned paper. That works, as long as OCR is turned on for that source (see
[getting-started.md](getting-started.md)).

## What you can skip

- **Appointment reminders, scheduling letters and portal messages** about logistics.
- **Bills, statements and insurance paperwork.** They add no clinical facts and are full of identifiers.
- **Consent forms, release-of-information forms, fax and cover pages.** Scanned pages with no text are dropped
  anyway.
- **Patient education handouts** and generic instruction sheets.
- **Images** (DICOM files, CD viewers). The written report is what's needed.

## File formats, best first

1. **C-CDA XML** ("download my record") and **PDFs with selectable text** (portal downloads, "print to PDF"). They are
   read exactly.
2. **Word documents and spreadsheets** (your own medication list, a lab export).
3. **Scanned PDFs, screenshots and images** (PNG, JPEG, TIFF). These are read with OCR when it's on for their folder:
   good on clean print and screenshots, less reliable on faxes, handwriting, tables and phone photos taken at an angle.
   When you can, ask for the original record instead.

To check a PDF, try selecting a word in it. If you can, it has text.

## Organizing the downloads

- **One folder per source** under `Sources/`: for example one for oncology notes, one for each hospital system, one
  for scanned older records, one for pharmacy records. Each is listed in `config/local.toml`
  ([getting-started.md](getting-started.md#5-add-the-real-records)).
- **Don't rename files to describe them.** Dates and note types are read from the content, and file names stay
  private anyway. Leave portal names as they are.
- **Add new records as they come.** [updating-records.md](updating-records.md) has the routine.

## A short checklist

- [ ] Each treating specialist's visit notes, at least the most recent and one from each change of treatment
- [ ] The oncology treatment plans or infusion records
- [ ] Every pathology and genetics report
- [ ] Imaging reports, especially those that showed progression or response
- [ ] A lab trend export, or the visit notes that contain the lab tables
- [ ] For each hospital stay: discharge summary, operative notes, implant log, and the full encounter export if
      offered
- [ ] Radiation treatment summaries
- [ ] Your current medication list, dated
- [ ] Vaccination records from the pharmacies and the state registry
- [ ] Older records from each medical records department, for the early history
