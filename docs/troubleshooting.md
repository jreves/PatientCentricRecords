# Troubleshooting and FAQ

Start with `python -m pipeline doctor`: it checks most of what can go wrong and says what to do.

## Ollama and the local model

**"Ollama is not responding at http://localhost:11434"**
Start the Ollama app: from the system tray on Windows, the menu bar on macOS, or `systemctl start ollama` on Linux.
Ollama may stop responding while it installs an update: let the update finish, start the app again, and rerun.

**The first run is very slow, or `doctor` says the model is only partly on the GPU**
- A server started with `ollama serve` in a terminal can come up CPU-only, several times slower. Quit it and start
  the app instead.
- If the GPU is simply too small for the model, `doctor` says so and suggests a model that fits. Smaller models are
  faster but missed names in testing, and caching makes later runs fast anyway.

**"Model qwen3:14b is not pulled"**
Run `ollama pull qwen3:14b`, or choose another model under `[llm]` in `config/local.toml`. `doctor` lists what's
installed.

**Does Ollama need to be running every time?**
Only when something isn't cached yet: new or changed documents for the pipeline, and new or changed statements for
the source audit. A rerun on unchanged records doesn't contact it.

## The pipeline

**It printed `NOT PUBLISHED`**
The leak check stopped it. Read `private/verify_report.md` locally.
- **FAIL** means a known identifier survived: check its spelling in `private/identifiers.toml`, or add the variant
  that survived.
- **WARN** means something looks like an identifier: check each one. When all are harmless, run
  `python -m pipeline run --accept-warnings`. That accepts only the warnings shown, and remembers them.

**A drug, test or clinic was removed as if it were a person**
Add it to `[allowlist] terms` in `config/local.toml`. If it's a generic medical term that any patient's records would
hit, add it to `config/medical_terms.txt` instead, and consider sending it upstream. `python -m pipeline audit` lists
redacted "people" that the local model thinks may be drugs or tests.

**A word is both part of a name and an ordinary word ("Will", "Page")**
Add it to `no_bare_match` in `config/local.toml`. It's still removed inside a full name, but not on its own.

**"all N page(s) are scans with no text (source '…')"**
That document is made only of scanned images, and its source doesn't have OCR on, so it's left out. Either set
`ocr = true` for that source (needs Tesseract), or get a text PDF of the document.

**Photos aren't read**
JPG and PNG files are skipped. Save them as PDF, as a scan or "print to PDF", and set `ocr = true` for the source.

**A note has the wrong date, or is marked ⚠**
Dates are read from labels like "Date of Service" in the *de-identified* text. `filtered/timeline.md` marks
low-confidence dates with ⚠. Claude Code can read those notes and tune the dating rules (`pipeline/chrono.py`).

**Windows: errors about long file names**
Portal file names can be very long. The pipeline handles that itself; if Windows still complains, enable long paths
(search "Enable Win32 long paths") or rename the files.

## The reports

**"No Chrome, Chromium or Edge found to print PDFs"**
Install one, or set `PCR_BROWSER` to the path of a Chromium-based browser.

**A PDF couldn't be written ("permission denied")**
The file is open in a viewer. Close it and rebuild.

**"skipped emergency_summary .docx"**
The editable Word file needs Node.js and `npm install` in the `reports/` folder. The PDF is built either way.

**The source audit takes a long time**
The first audit asks the local model about every statement, which is about ten seconds each. Later audits re-check
only what changed. `python -m reports audit --no-semantic` skips the model's reading altogether.

**The source audit says the model doubted a statement that's plainly right**
It happens. See [source-audit.md](source-audit.md#when-the-model-doubts-a-statement): check the passage, then add a
`reviewed:` note saying where the fact is.

## Claude Code

**"This project's Sources/ and private/ folders hold raw patient data…" (a refused command)**
That's the privacy hook. It refuses any command that names those folders, including a harmless one like an `echo`.
- If Claude needs something from there, the answer is a pipeline command, which prints counts only, or the family
  checking the file and reporting back.
- Don't disable the hook.
- If it refuses a command that only used one of those words in a sentence, rephrase it.

**Claude wants to read the raw records or `private/identifiers.toml`**
Say no. The project is set up so it never needs to. If you're not sure whether a request is safe, ask it to explain
which files it will read.

## Privacy questions

**Is this HIPAA-compliant?**
HIPAA's rules govern healthcare providers and insurers, not a family using a patient's own records. This tool also
keeps clinical dates, so it isn't HIPAA "Safe Harbor" de-identification. See the README.

**Can I share the reports?**
They're the patient's health information: share them deliberately, with the people who need them. They name
clinicians and facilities and carry full clinical dates, but not the patient's name, date of birth or record
numbers.

**I found identifying information in the published output**
Add it to `private/identifiers.toml` and rerun; the leak check will then guard it. If it slipped through because of a
pattern the pipeline doesn't catch, please report it privately (see [SECURITY.md](../SECURITY.md)), with an invented
example of the pattern, never the real text.
