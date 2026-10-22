# How de-identification works

Everything here runs locally. The goal: remove what identifies the patient and the people around her, and keep what
the treatment history needs.

## What is removed and what is kept

| Removed (token) | Kept |
|---|---|
| the patient's names → `[PATIENT]` | diagnoses, staging, biomarkers, genes, drugs, doses, trial names |
| family, caregivers, contacts → `[PERSON-nn]` | clinical dates (the sequence is the point) |
| date of birth → `[DOB; age 61]` | the patient's age on each note's date (90+ shown as "90+") |
| record, account, member, accession and specimen numbers; device serial and lot numbers → `[ID]` | clinician names (`redact_clinicians = true` to remove them); implant catalog numbers and GS1 device identifiers (they name the product, not the patient's device) |
| phone and fax numbers → `[PHONE]`, emails → `[EMAIL]`, URLs → `[URL]` | facility and practice names (`redact_facilities = true` to remove them) |
| street addresses → `[ADDRESS]`; "City, ST" → `[LOCATION]` | states on their own; facility names containing a town |

Clinic phone numbers and addresses are removed too, because a rule can't tell them from the patient's own.

Because clinician names are published, ambiguous people are treated as private: anyone who shares the patient's
surname, anyone listed in `private/identifiers.toml`, and any tie between "clinician" and "other person" is
redacted.

## Detection: three independent layers

1. **Rules** (`pipeline/rules.py`): labelled names ("Provider: …", "Signed by …", "Dr. X", "X, MD"), date of birth,
   labelled IDs, phones, emails, URLs, street addresses, "City, ST ZIP", long digit runs.
2. **Your list** (`private/identifiers.toml`): every name, nickname, number and address you enter is redacted
   everywhere, in any capitalization. The date of birth is matched in all its common formats.
3. **A local language model** through Ollama: it reads each page in chunks and lists people, organizations,
   addresses and IDs. Its *labels* are unreliable (models call relatives "facilities" and drugs "people"), so the
   pipeline uses only what the model flags, after these checks: the text is found verbatim, it fits its category (a
   phone needs digits, an email an @), it isn't a lowercase "name", and it isn't in `config/medical_terms.txt` or the
   allowlist.

Then **propagation**: every name found anywhere is searched for everywhere, as "First Last", "Last, First", with
middle initials, and as a bare surname or first name (capitalized only). This catches the page where the model missed
a name it found elsewhere. IDs found by a rule are propagated the same way.

**Scanned records and image files** (PNG, JPEG, TIFF) are OCR'd with Tesseract. OCR misreads letters ("Th0rnbury"), so known names and numbers are also
matched fuzzily in OCR'd text, and the leak check repeats that.

## The registry

`private/registry.json` links the variants of each person ("Dr. Chen", "CHEN, LI", "Chen") to one entity with a
stable token, so `[PERSON-03]` means the same person in every note and across runs. The patient comes from
`identifiers.toml` or, failing that, from the full name the model most often labels as the patient. Relatives who
share her surname stay separate entities, because first names must agree.

## The leak check (`pipeline/verify.py`)

Before anything reaches `filtered/`:

- **FAIL** if any identifier from `identifiers.toml`, or any registry name, is still present. This always blocks
  publishing.
- **WARN** on text that looks like an identifier: digit runs, phone shapes, capitalized name-like words after
  "Dr.", "Mr.", and so on. Warnings block publishing until you review them in `private/verify_report.md` and run
  `python -m pipeline run --accept-warnings`. That accepts only the warnings shown, and remembers them.

## Chronology

After redaction, each note's date, type and clinic are read from the redacted text (`pipeline/chrono.py`), so they
can be tuned by reading the published output. Low-confidence dates are marked ⚠ in `filtered/timeline.md`.
Hospital encounter exports (one long PDF per stay) are split into one document per section: H&P, discharge summary,
notes, labs, orders. C-CDA XML episode summaries are dated by the episode, not the print date.

Duplicates are dropped before the model runs: the same visit as XML and PDF, or a re-download (`pipeline/dedup.py`).
XML is preferred, because PDF tables scramble the word order.

## Tuning

1. Open `private/review/index.html`: red = names, blue = organizations, yellow = other identifiers.
2. **Missed** something? Add it to `private/identifiers.toml` and rerun. If it's a *pattern* (a label format the rules
   don't know), add a synthetic test case to `tests/` and fix the rule.
3. **Over-redacted** a drug, test, lab or device? Add it to `[allowlist] terms` in `config/local.toml`. If it's
   generic (any patient would hit it), add it to `config/medical_terms.txt` instead.
4. A word that is both part of a name and an ordinary word ("Will", "Lincoln") goes in `no_bare_match`. It is still
   redacted inside a full name.
5. `python -m pipeline audit` lists redacted "people" the model thinks may be drugs or tests, as counts. The words
   go to `private/audit_suspects.md` for you to confirm. Don't exempt a word only on the model's say-so.

Reruns use the caches and take seconds, so tuning is cheap.
