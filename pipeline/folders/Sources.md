# Sources: the raw records (private)

Put the patient's records here, one subfolder per source, for example:

```
Sources/
  clinical-notes/      visit notes downloaded from the patient portal (PDF)
  hospital-records/    hospital summaries (C-CDA XML is better than the PDF printout)
  scanned-records/     scanned paper records (PDF; set ocr = true for this source)
```

Then list each subfolder as a `[[sources]]` block in `config/local.toml`. Readable types: PDF (with a text layer, or
scanned with `ocr = true`), Word `.docx`, Excel `.xlsx`, C-CDA `.xml`, and `.txt`.

**This folder never leaves your computer.** It is git-ignored, and Claude Code is blocked from reading it, searching
it or listing its file names (`.claude/settings.json` and the hook in `.claude/hooks/`). Only the local pipeline reads
it: `python -m pipeline run`. Portal file names can contain names and record numbers, so don't paste them into a
chat either.
