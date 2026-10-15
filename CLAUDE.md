# PatientCentricRecords

De-identify a patient's medical records **locally**, order them chronologically, and only then use hosted Claude to
analyze the treatment history and build reports. See README.md for the overview and docs/ for details.

## The one rule: raw PII never reaches hosted Claude

Claude (you) is hosted. Anything you read, grep, or see in command output leaves this machine. Therefore:

- **Never read, grep, cat, head, list, or open** anything in `Sources/` or `private/`. `.claude/settings.json` denies
  Read/Edit/Write there, and `.claude/hooks/guard_private.py` refuses shell commands and searches that name either
  folder. Don't try to work around the hook. If it blocks something you need, ask the user.
- File *counts, sizes, and types* are fine (`python -m pipeline doctor` reports them). **Never print file names**
  from those folders, not via `ls`, `git status`, error messages, or scripts. Portal file names can contain the
  patient's name, record numbers, or access tokens.
- **Never write code that prints note text, LLM output, or matched identifiers to the console.** Pipeline stdout is
  counts and doc ids only; details go under `private/`. Exceptions must not echo content either (see `llm.py`: model
  output is never included in an error).
- Read `filtered/` only after a run printed `PUBLISHED`, meaning the leak check passed. If it printed
  `NOT PUBLISHED`, don't look in `private/staging/`. Ask the user to review `private/verify_report.md` and
  `private/review/index.html`, and to report back.
- `private/identifiers.toml` is filled in **by the user**. Never edit it, never ask to see it, and never suggest
  values for it from what you've read.
- To reproduce or debug a detection problem, write a **synthetic** fixture in `tests/fixtures/` with invented
  identifiers. Never copy real text into tests, commits, issues, or messages, even de-identified text.
- The local LLM must stay local: `llm.url` is localhost only (the client refuses anything else).
- Analysis outputs (`analysis/`) are clinical content: keep them local. Don't publish them as artifacts or upload them
  anywhere.

## Layout

```
Sources/<source>/     raw records: PDF, docx, xlsx, C-CDA XML, scans       [git-ignored, Claude-denied]
private/              identifiers.toml (user-filled), registry.json, cache/, staging/, review/,
                      verify_report.md, source_map.json                    [git-ignored, Claude-denied]
filtered/             PUBLISHED de-identified output: notes/, timeline.md, all_notes_chronological.md,
                      all_documents_chronological.md, manifest.json       [git-ignored; readable after PUBLISHED]
analysis/             case/ (the case file) and the built reports          [git-ignored]
config/               pipeline.toml (shared), local.toml (this machine, git-ignored), templates, medical_terms.txt
pipeline/             de-identification (python -m pipeline ...)
reports/              report engine (python -m reports build)
examples/case/        a fictional case file
docs/                 de-identification.md, case-file.md, working-with-claude.md
tests/                synthetic fixtures + regression tests
```

## Commands

```bash
python -m pipeline init                # data folders + private/identifiers.toml + config/local.toml from templates
python -m pipeline doctor [--bench]    # Python, GPU, Ollama + model choice, Tesseract, Node, browser
python -m pipeline run                 # full run; publishes only if the leak check is clean
python -m pipeline run --accept-warnings   # only after the USER has reviewed every WARN
python -m pipeline run --limit 2       # quick trial
python -m pipeline run --no-llm        # rules only, never publishes (debugging)
python -m pipeline verify              # re-check published output, e.g. after adding identifiers
python -m pipeline audit               # count-only report of redacted 'people' that may be drugs/tests
python -m pipeline ids                 # count-only inventory of detected IDs; values go to private/ for the user
python -m reports build [--only NAME]  # reports from analysis/case (or --case DIR)
python -m pytest -q                    # synthetic regression tests
```

Reruns hit the caches in `private/cache/` (llm/, text/, ocr/) and take seconds, so tuning is cheap. Each run prints
`[timing]` per phase. Ollama is contacted only for text that isn't cached. Changing the model or `PROMPT_VERSION` in
`llm.py` invalidates the model cache.

## How it works

See docs/de-identification.md. In short:
- Three detection layers are unioned: rules (`rules.py`), the user's identifier list, and the local LLM (`llm.py`).
  The LLM's type labels are unreliable, so `core.locate_llm` keeps only verbatim, category-sane surfaces that aren't
  clinical terms. Don't reroute failures to name handling: that once turned ~2,000 clinical terms into "people".
- Every name and rule-found ID is propagated everywhere (`names.Registry`).
- Date, type and clinic are derived from the **redacted** text (`chrono.py`), so they can be tuned by reading
  published output.
- Then the leak check (`verify.py`).

Policy (`config/pipeline.toml [policy]`): clinical dates kept, DOB removed but age kept, clinician and facility names
kept by default; the patient's family, contacts, IDs, phones, addresses and "City, ST" geography removed.

## Tuning loop

1. The user reviews `private/review/index.html` (red = names, blue = orgs, yellow = other).
2. Missed PII → the user adds it to `private/identifiers.toml`. A false positive → `[allowlist] terms` in
   `config/local.toml` (patient-specific words, e.g. her clinics) or `config/medical_terms.txt` (generic terms only).
   A word that's both a name part and an ordinary word → `no_bare_match`.
3. Rerun. When a problem is a *pattern*, add a synthetic regression case to `tests/` and fix the rule.
4. `python -m pipeline audit`: the user confirms `private/audit_suspects.md`. Never auto-exempt a word on the
   model's guess.
5. Claude can tune chronology and note types by reading published `timeline.md` and notes: check ⚠ dates,
   `no date found`, and `note`-typed documents.

## Reports

The engine (`reports/`) holds no patient facts. Everything comes from the case file (docs/case-file.md). Write the
case only from `filtered/`. Every printed page carries the case's disclaimer. Check the rendered PDFs visually
(render pages to PNG and look) for overflow and label collisions before calling a report done.

## Working conventions

- Keep **HISTORY.md** current (it is this installation's log, git-ignored in the public repo): a dated entry for
  every session that changes behavior, policy, or results. Stats only, never content.
- `.gitignore` is an **allowlist**. Never widen it for data. **Never `git add -A`**: stage explicit paths. To look at
  git state, use `git status --short -- pipeline reports config tests docs examples .claude`.
- Don't name the raw or private folders in commit messages or shell commands (the hook refuses them).
- Bump `PIPELINE_VERSION` in `pipeline/config.py` when the output format or redaction behavior changes.
- New sources: add a `[[sources]]` block in `config/local.toml`. New file types: add a reader in `extract.py`.
- Code must run on Windows, macOS and Linux (paths via pathlib; `long_path` only on Windows).
