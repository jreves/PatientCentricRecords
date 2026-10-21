# Getting started

This guide takes you from a fresh computer to your first reports. The setup takes about an hour, most of it
installing tools and downloading the local model. You don't need to be a programmer, but you'll type a few
commands in a terminal.

- [1. Install the tools](#1-install-the-tools)
- [2. Get PatientCentricRecords](#2-get-patientcentricrecords)
- [3. Check your computer](#3-check-your-computer)
- [4. Try it on the example patient](#4-try-it-on-the-example-patient)
- [5. Add the real records](#5-add-the-real-records)
- [6. De-identify them](#6-de-identify-them)
- [7. Write the case file with Claude](#7-write-the-case-file-with-claude)
- [8. Build the reports and check the source audit](#8-build-the-reports-and-check-the-source-audit)

> [!IMPORTANT]
> Steps 1–4 involve no patient data at all. Do them first: if something doesn't work, you'll find out before any real
> records are on the computer.

## 1. Install the tools

| Tool | Why | Windows | macOS | Linux |
|---|---|---|---|---|
| **Python 3.11 or newer** | runs everything | [python.org](https://www.python.org/downloads/); tick "Add python.exe to PATH" | `brew install python` or [python.org](https://www.python.org/downloads/) | usually installed; else `sudo apt install python3 python3-venv` |
| **Git** | downloads the project | [git-scm.com](https://git-scm.com/download/win) | `xcode-select --install` | `sudo apt install git` |
| **[Ollama](https://ollama.com/download)** | the local model that finds names | the installer; it runs in the system tray | the app; it runs in the menu bar | `curl -fsSL https://ollama.com/install.sh \| sh` |
| **[Claude Code](https://docs.claude.com/en/docs/claude-code/overview)** | helps write the case file from the de-identified notes | see its setup page | see its setup page | see its setup page |
| Chrome, Edge or Chromium | prints the reports to PDF | Edge is already installed | [Chrome](https://www.google.com/chrome/) | `sudo apt install chromium` |
| Tesseract *(optional)* | reads scanned records | [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) | `brew install tesseract` | `sudo apt install tesseract-ocr` |
| Node.js *(optional)* | the editable Word version of the emergency summary | [nodejs.org](https://nodejs.org) | `brew install node` | `sudo apt install nodejs npm` |

Then download the local model. It's about 9 GB, so give it time:

```bash
ollama pull qwen3:14b
```

Not sure your computer can run it? Do step 3 first: `python -m pipeline doctor` checks your GPU and suggests a model
that fits. It never downloads anything itself.

## 2. Get PatientCentricRecords

```bash
git clone https://github.com/jreves/PatientCentricRecords.git
cd PatientCentricRecords
python -m venv .venv
```

Activate the environment. Do this every time you open a new terminal for the project:

| Windows (PowerShell) | macOS / Linux |
|---|---|
| `.venv\Scripts\Activate.ps1` | `source .venv/bin/activate` |

Then install the project and create its folders:

```bash
pip install -e ".[ocr,dev]"
python -m pipeline init
```

`init` creates four folders, each with a README explaining it:
- `Sources/` for the raw records;
- `private/` for the identifiers and working files;
- `filtered/` for the de-identified notes;
- `analysis/` for the case file and the reports.

It also creates two files for you to edit: `private/identifiers.toml` and `config/local.toml`. All of these are
ignored by git.

For the editable Word file, also run `npm install` inside the `reports/` folder.

## 3. Check your computer

```bash
python -m pipeline doctor
```

It reports:
- Python and its packages;
- memory and GPU;
- whether Ollama is running, and which installed model suits your GPU;
- Tesseract, Node and a PDF browser;
- your configured sources, counting files only.

Fix anything marked **FAIL**. **WARN** items are optional.

To see how well and how fast the model works on your machine, run `python -m pipeline doctor --bench`. It scores the
model on a built-in note with invented names.

> [!TIP]
> On Windows and macOS, start Ollama from its app (tray or menu bar), not with `ollama serve` in a terminal. A server
> started from a terminal can end up running on the CPU only, several times slower. `doctor` shows how much of the
> model is on the GPU.

## 4. Try it on the example patient

```bash
python -m reports build --case examples/case --out examples/out
```

This builds every report for a fictional patient. Open the PDFs in `examples/out/` to see what you'll get for your
own records. The last one, `source_audit_*.pdf`, shows where each statement comes from.

## 5. Add the real records

1. **Download the records.** Patient portals usually offer each visit note as a PDF. Many also have a "download my
   record" or "View, Download, Transmit" export, which gives C-CDA XML; prefer that for hospital summaries, because
   it's read more accurately than a PDF printout. Scanned paper records work as PDFs. Phone photos (JPG/PNG) don't:
   save them as PDF first.
2. **Put them in subfolders of `Sources/`**, one per source, for example `Sources/clinical-notes`,
   `Sources/hospital-records` and `Sources/scanned-records`.
3. **List each subfolder in `config/local.toml`**, as a `[[sources]]` block (the file shows how). Add `ocr = true`
   for scanned records.
4. **Fill in `private/identifiers.toml` yourself**, in a text editor: the patient's names (including maiden name and
   nicknames), date of birth, record numbers, address, phone numbers, and the names of family members and contacts.
   Everything you list is removed everywhere, and the leak check fails if any of it survives.

> [!WARNING]
> Don't ask Claude to fill in `private/identifiers.toml`, and don't paste its contents, or any raw record, into a
> chat. Claude Code is blocked from reading `Sources/` and `private/`; keep it that way.

## 6. De-identify them

```bash
python -m pipeline run
```

The first run is slow, a few minutes per long note on a GPU, because the local model reads every page. Every result
is cached, so later runs take seconds. The run prints only counts and document ids, never text from the records.

How the run ends:

| It prints | Meaning | What to do |
|---|---|---|
| `PUBLISHED N notes` | the leak check passed | go on to step 7 |
| `NOT PUBLISHED` with `FAIL` | a known identifier survived | read `private/verify_report.md`, add what's missing to `private/identifiers.toml`, and run again |
| `NOT PUBLISHED` with `WARN` | something looks like an identifier | check each one in `private/verify_report.md`; when they're all harmless, run `python -m pipeline run --accept-warnings` |

Then open **`private/review/index.html`** in your browser. It shows the original text with every redaction
highlighted: red for names, blue for organizations, yellow for other identifiers. Look for anything missed, which
goes into `private/identifiers.toml`, and for anything wrongly removed, such as a drug taken for a name, which goes
into `[allowlist]` in `config/local.toml`. Run again after each change; it only takes seconds.
[de-identification.md](de-identification.md) explains the details.

## 7. Write the case file with Claude

The reports are built from a **case file**: the patient's history as structured facts (treatments, events, scans,
results), each citing the note it comes from. Claude drafts it from the de-identified notes, and you check it.

Open Claude Code in the project folder and ask, for example:

> Read `filtered/all_notes_chronological.md` and draft `analysis/case/` following `docs/case-file.md`, starting from
> `examples/case/`. Cite the note behind each statement in `analysis/case/citations.yaml`.

Then read what it wrote, against the records and what you know. It can misread a note, miss a treatment, or merge two
events. Correct it in conversation ("the radiation was in 2007, by Dr. X") and say when something is a family report.
[working-with-claude.md](working-with-claude.md) has more examples, and [case-file.md](case-file.md) describes every
part of the case file.

## 8. Build the reports and check the source audit

```bash
python -m reports build
```

The reports appear in `analysis/`. The build ends with **`source_audit_<date>.pdf`**. It lists every statement in the
reports with the record note it comes from, the checks it passed, and anything that needs your attention.
[source-audit.md](source-audit.md) explains how to read it. Fix what it flags before handing the reports to a new
physician.

When new records arrive, [updating-records.md](updating-records.md) walks through the routine. If something goes
wrong, see [troubleshooting.md](troubleshooting.md).
