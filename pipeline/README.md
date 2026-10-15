# pipeline: local de-identification

`python -m pipeline <command>`. Runs entirely on this machine. The only network connection is to the local Ollama
server, and `llm.url` must be localhost. Console output is counts and document ids only: note text, model output and
matched identifiers are written to `private/`, never printed.

**Flow** (`core.py`): extract → deduplicate → detect → build the name registry → redact → date and classify → leak
check → publish.

| Module | Role |
|---|---|
| `extract.py` | Reads each source: PDF text (pdfplumber), `.docx`, `.xlsx`, `.txt`, C-CDA XML (`ccda.py`); scanned pages through `ocr.py`. A document's id is a hash of its content. |
| `ccda.py` | C-CDA XML reader built as an allowlist: from the header it emits only the document kind, title, dates and the custodian/location. The patient block, authors, addresses and phones are never extracted. |
| `ocr.py`, `fuzzy.py` | Local Tesseract OCR for scanned pages, and fuzzy matching of known identifiers in OCR text (which misreads letters). |
| `dedup.py` | Drops content duplicates (the same visit as XML and PDF, re-downloads) and records documents quoted inside others. |
| `rules.py` | Pattern detectors: labelled names ("Provider:", "Dr. X", "X, MD"), date of birth, labelled IDs, phones, emails, URLs, addresses, plus the known identifiers from `private/identifiers.toml`. |
| `llm.py` | Asks the local model for names, organizations, addresses and IDs. Its type labels are unreliable, so `core.locate_llm` keeps only surfaces found verbatim that pass a sanity check for their kind and aren't clinical terms. |
| `names.py` | The pseudonym registry: links "Dr. Chen", "CHEN, LI" and "Chen" to one entity with a stable token, and searches every name everywhere. |
| `chrono.py`, `sections.py` | The note's date, type and clinic, read from the *redacted* text; hospital encounter exports split into sections. |
| `verify.py` | The leak check: FAIL on any known identifier or registry name left; WARN on identifier-shaped text. Either one blocks publishing. |
| `audit.py`, `idreport.py` | Count-only reports that help you tune: redacted "people" that may be drugs; record numbers found. Words go to `private/`. |
| `doctor.py` | The environment check and model chooser. |
| `folders/` | READMEs that `init` puts in the data folders. |

Bump `PIPELINE_VERSION` in `config.py` when the output format or redaction behavior changes. Changing the model or
`PROMPT_VERSION` in `llm.py` invalidates the model cache.
