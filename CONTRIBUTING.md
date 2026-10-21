# Contributing

Thank you for helping. This project exists for patients and families, so contributions are judged first by one
question: does this keep the patient's data private and in their control?

## The one rule

**Never put real patient information anywhere in this repository or its issues**: not in code, tests, fixtures,
commits, pull requests, screenshots or discussions, and not even de-identified text. Describe problems with invented
examples, and build tests the same way (see `tests/fixtures/synthetic/`). If you've found a privacy leak, report it
privately ([SECURITY.md](SECURITY.md)).

## Setting up

```bash
git clone https://github.com/jreves/PatientCentricRecords.git
cd PatientCentricRecords
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[ocr,dev]"
python -m pytest -q
python -m reports build --case examples/case --out examples/out
```

The tests use only invented records and need no GPU. The OCR test skips without Tesseract.

## Making a change

- **Keep the privacy properties:**
  - Pipeline output (stdout) is counts and document ids only. Never print record text, model output or matched
    identifiers, even in error messages.
  - The local model's URL stays localhost-only.
  - Don't widen `.gitignore`, which is an allowlist.
- **Add a regression test** for any detection or redaction change, built on a synthetic fixture with made-up names and
  numbers in the same *shape* as the problem.
- **Bump `PIPELINE_VERSION`** in `pipeline/config.py` when published output or redaction behavior changes.
- **Run on Windows, macOS and Linux:** use `pathlib`, no shell-specific commands, and test what you can.
- **Match the surrounding code:** its naming, its comment density, and its plain-language messages.
- **Update the docs:** the README for any user-visible change, `docs/case-file.md` for any case-file key, and
  `CHANGELOG.md`.

## Ideas that would help

- Readers for more record formats (other EHR exports, more hospital systems' PDF layouts).
- Dating and note-type rules for practices beyond the ones tested.
- Report types for other cancers, or for non-cancer conditions.
- Languages other than English.
- Accessibility improvements to the reports.

## Pull requests

1. Describe what changed and why, with invented examples.
2. Confirm that `python -m pytest -q` passes and that the example case still builds.
3. Confirm that no real patient information is anywhere in the change.

By contributing, you agree that your contribution is licensed under the [Apache License 2.0](LICENSE).
