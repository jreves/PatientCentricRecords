# Working with Claude

Claude Code runs on your computer, but the model is hosted: anything it reads, searches, or sees in command output
is sent to Anthropic. This project is set up so that what it sees is the de-identified output only.

## What protects the raw data

- **Permission rules** (`.claude/settings.json`) deny Claude's Read, Edit and Write tools in `Sources/` and `private/`.
- **A hook** (`.claude/hooks/guard_private.py`) refuses any shell command, search or file operation that names those
  folders. That covers `cat`, `grep`, `ls`, and scripts that open files there. It errs on the side of refusing.
- **The pipeline prints counts only.** Note text, model output and matched identifiers go to `private/`, never to the
  console, so running `python -m pipeline run` shows Claude nothing private.
- **`CLAUDE.md`** tells Claude the rules: read `filtered/` only after a run printed `PUBLISHED`; never print file
  names from `Sources/` (portal file names can contain names and record numbers); never copy record text into tests or
  commits.

These are guardrails, not guarantees. Don't paste raw records, file names, or anything from `private/` into the chat
yourself.

## Good uses

- "Read `filtered/timeline.md` and tell me which notes have uncertain dates."
- "From `filtered/all_notes_chronological.md`, draft `analysis/case/treatment.yaml`: every systemic treatment with
  start and stop dates, and the reason it stopped."
- "Which notes mention the PIK3CA result, and do they agree?"
- "The review page shows a drug name redacted as a person. Add it to the allowlist in `config/local.toml`."
- "Rebuild the reports with today's date."

## Things to check yourself

- Every fact in the case file, against the records and what the family knows. Claude can misread a note, miss a
  treatment, or merge two events.
- The review page, `private/review/index.html`, after each run that adds records.
- Each report, before you share it.

## Your account's data settings

Check your Claude account's privacy settings, for example whether your conversations may be used to improve models,
and choose what you're comfortable with for health information. The de-identified notes still describe a person's
health in detail.
