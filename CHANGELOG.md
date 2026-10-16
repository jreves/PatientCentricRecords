# Changelog

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
