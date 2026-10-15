# filtered: the de-identified notes

Written by `python -m pipeline run`, and only when the leak check passes (the run prints `PUBLISHED`). Each publish
replaces this folder's files, including this README.

| File | What it is |
|---|---|
| `notes/YYYY-MM-DD_type_docid.md` | One note per document (or per section of a hospital export), with a header: date and how it was found, type, clinic, the patient's age, source, redaction count. |
| `timeline.md` | Every note by date (⚠ marks low-confidence dates). |
| `all_notes_chronological.md` | The clinical notes in one file, for a long-context AI session. |
| `all_documents_chronological.md` | Everything, including hospital orders, flowsheets and medication records. |
| `manifest.json` | Machine-readable index. |

These files are what hosted Claude reads to answer questions and write the case file for the reports. Names of the
patient, family and contacts are replaced by tokens (`[PATIENT]`, `[PERSON-02]`, `[DOB; age 61]`, `[ID]`...);
clinicians, facilities, clinical dates, drugs and results are kept. **De-identification is never perfect**: treat
this folder as sensitive, keep it git-ignored, and skim the review page in `private/review/` before sharing anything.
