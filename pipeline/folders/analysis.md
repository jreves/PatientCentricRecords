# analysis: the case file and the reports

```
analysis/
  case/            the case file: YAML facts + document.html narrative + citations.yaml (see docs/case-file.md)
  *.pdf, *.html    built reports (python -m reports build), ending with source_audit_<date>.pdf
  .work/           intermediate HTML and the headless browser profile
```

The case file is written from the de-identified notes in `filtered/`, usually by asking Claude Code to draft it
("read filtered/all_notes_chronological.md and fill in analysis/case/treatment.yaml"), then checked and corrected by
the family. The reports are built from the case file alone: `python -m reports build`. Every statement in the case
cites the published note it comes from (`citations.yaml`), and each build ends with a source audit that checks those
citations and lists every statement with its source, for the family to review before sharing the reports.

This folder holds clinical content about one person, so it is git-ignored. Share the finished PDFs deliberately, with
the people who need them.
