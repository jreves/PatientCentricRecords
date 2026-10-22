# Changelog

## Unreleased

- **Documentation:** a getting-started guide (Windows, macOS, Linux), a routine for new records, a guide to the source
  audit, an architecture overview with a diagram, troubleshooting and FAQ, CONTRIBUTING and SECURITY.
- **Gathering records:** a guide to which portal records are worth downloading, and how detailed.
- **Image files:** PNG, JPEG and TIFF (one page per frame) are read with OCR in sources with `ocr = true`, so a report
  that exists only as a screenshot can be used. Screenshots are enlarged before recognition. "XR"/"XRAY" reports are
  typed as imaging.
- **Example case:** now covers every report, with generated fictional notes (lab tables, vital signs, medication
  lists, running history) and citations. The README shows screenshots from it.
- **Implants:** a case can list implanted devices (component, specification, manufacturer, catalog number, status),
  shown with the new `implants` table kind. De-identification keeps what a surgeon needs: GS1 device identifiers and
  catalog numbers (they name the product, not the patient's device), including unlabelled repeats in an implant log.
  Serial and lot numbers are still redacted; "Lot no." is now an ID label.
- **Fixes:**
  - "female" and "male" are medical terms, so a stray registry entry can't redact them as a name.
  - The source audit no longer strips "<...>" from note text, which had deleted text between a lab range's "<" and a
    later ">".
  - A document made only of scanned pages no longer breaks a run; the log names its source.
  - Unreadable model answers are cached, so audits don't re-ask.
  - The vitals subtitle no longer says "rose to a peak" when the first weight is the peak.

## 0.9.0 (continued, before the first push)

- **Source audit** (`python -m reports audit`, run after every build): every statement in a case cites a published
  note and a verbatim quote, a family report, or a records-wide search for "not in the records". The local checks
  confirm the quote and every date, dose, drug and clinician. The local model then reads each statement fact by
  fact. A case can mark notes as authoritative for what they cover, and record hand-review notes. The appendix PDF
  lists every statement with its sources, worklist first.
- **De-identification:** specimen accession numbers in lab-order logs and implant device IDs are now redacted.
- **Word files:** headers and footers are read, and an "Updated <date>" line dates a document.
- **Privacy hook:** a bare folder name in prose no longer trips it.

## 0.9.0 (first public release)

- **De-identification pipeline** (`python -m pipeline`): runs locally. It reads PDF (text and scanned, with
  Tesseract OCR), Word, Excel, plain text and C-CDA XML records. Detection combines rules, the user's identifier
  list and a local model through Ollama, with corpus-wide propagation of every name and ID. A leak check gates
  publishing. Output is chronological de-identified notes with dates, note types and the patient's age.
- **`pipeline doctor`**: checks Python, RAM and GPU memory (NVIDIA, AMD, Apple Silicon, CPU) and Ollama, picks the
  best installed tested model or suggests one (it never downloads), and checks the optional tools. `--bench`
  scores a model on a synthetic note.
- **Report engine** (`python -m reports build`): treatment timelines (interactive and PDF), a treatments table,
  pathology and genomics, blood counts, vitals, a medication timeline, a disease overview, open questions, and an
  emergency summary (PDF and Word). Everything is driven by a per-patient case file.
- **Privacy guardrails for Claude Code**: permission deny rules and a hook that refuses shell access to the raw and
  private folders.
- A fictional example case, and regression tests on invented records only.
