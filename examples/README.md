# examples

`case/` is a complete case file for an **invented** patient: every name, date and value is fictional. Use it to see
what the reports look like before you have your own case, and as a starting point for writing one.

```bash
python -m reports build --case examples/case --out examples/out
```

It builds the cancer timeline (an interactive page and a PDF), the treatments table, the open-questions page and the
emergency summary, then the source audit (`source_audit_<date>.pdf`). `case/notes/` holds one fictional de-identified
note with a lab table, so the emergency summary has blood counts to show. `case/citations.yaml` cites a few of the
example's statements, to show each audit status (grounded, partly grounded, family report, no source yet).
A real case's `notes_dir` is the pipeline's `filtered/notes`.

`out/` is git-ignored.
