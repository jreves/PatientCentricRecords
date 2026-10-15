# tests

`python -m pytest -q`

Every test uses **invented** records: synthetic notes in `fixtures/synthetic/`, a synthetic C-CDA document in
`fixtures/ccda/`, and the fictional example case in `examples/case/`. Never copy real record text into a test, even
de-identified. To reproduce a detection problem, write a new synthetic fixture with made-up names and numbers that
have the same *shape* as the problem.

| File | Covers |
|---|---|
| `test_pipeline.py` | detection, redaction, the registry, dates and note types, deduplication, OCR fuzzy matching, the leak check |
| `test_config.py` | merging `config/local.toml`, platform paths |
| `test_doctor.py` | model choice by GPU memory, the localhost-only rule for the model URL |
| `test_guard.py` | the Claude Code privacy hook |
| `test_reports.py` | the report engine on the example case (HTML, no browser needed) |

The OCR test needs Tesseract and skips without it.
