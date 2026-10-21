# Security and privacy reports

## What to report privately

Please report these privately, not in a public issue:

- **Identifying information reaching published output**: a pattern of name, number, address or date the pipeline
  doesn't remove (the "leak check" didn't catch it).
- **The privacy guardrails being bypassed**: a way for Claude Code to read the raw-records or private folders despite
  the permission rules and the hook.
- **Data leaving the computer when it shouldn't**: for example, raw text sent anywhere other than the local model.
- Any other vulnerability in the code.

## How

Use **[Report a vulnerability](https://github.com/jreves/PatientCentricRecords/security/advisories/new)**, under the
repository's Security tab. Only the maintainers can see the report.

Include:
- what happened, and what you expected;
- **an invented example** that shows the same pattern (for example "a line like `Ref: Jane Q. Doe-Smith` keeps the
  hyphenated surname"), never the real text, file names or screenshots of real records;
- your operating system, the version or commit, and the model from `python -m pipeline doctor`.

## What happens next

This is a volunteer project, so there's no fixed response time. Privacy reports come first. We'll confirm the
problem, fix it with a regression test built on the invented example, and credit you in the changelog if you'd like.

## Supported versions

Fixes go into the latest `main`. Update with `git pull` and rerun `python -m pipeline run`: if a fix changes
redaction, the leak check and the published notes update on the next run.
