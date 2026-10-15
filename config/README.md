# config

| File | In git | What it is |
|---|---|---|
| `pipeline.toml` | yes | Shared defaults: the local model and its settings, the de-identification policy, deduplication thresholds, a generic allowlist. Nothing in it may identify a patient. |
| `local.toml` | **no** | This installation's settings, merged over `pipeline.toml`: the list of `Sources/` subfolders, words wrongly redacted in *your* records, a different model or Tesseract path. Created from `local.example.toml` by `python -m pipeline init`. |
| `local.example.toml` | yes | The template for `local.toml`. |
| `identifiers.example.toml` | yes | The template for `private/identifiers.toml`, where you list the patient's real identifiers. |
| `medical_terms.txt` | yes | Drug, test and other clinical words that must never be treated as names. Add generic terms here (and send them upstream). |
| `medical_terms.local.txt` | **no** | Optional additions for your records only. |

## How `local.toml` is merged

- `[[sources]]` in `local.toml` **replaces** the example source in `pipeline.toml`.
- `[allowlist] terms` and `no_bare_match` are **added** to the shared lists.
- Any other key **overrides** the shared value (for example `[llm] model`).

Set `PCR_LOCAL_CONFIG` to use a different overlay file.

## Settings worth knowing

- `[llm] url` must point at this machine. The pipeline refuses any other host, because raw text is sent to it.
- `[policy] dates = "keep"` keeps clinical dates. The date of birth is always removed, and the age on each note's date
  is kept.
- `[policy] redact_clinicians` / `redact_facilities` (default `false`): set them to `true` to replace clinician and
  facility names with `[CLINICIAN-nn]` / `[FACILITY-nn]` too.
- `[allowlist] no_bare_match`: words that are part of someone's name but also ordinary words ("Will", "Page"). They are
  still redacted inside a full name, but not on their own.
