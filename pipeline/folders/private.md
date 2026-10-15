# private: identifiers and working files (private)

Everything here contains the patient's identifying information. It is git-ignored, and Claude Code is blocked from
reading it.

| File | What it is |
|---|---|
| `identifiers.toml` | **You fill this in**: the patient's names (including maiden and nicknames), date of birth, record numbers, address, phones, family and contacts. The pipeline redacts every one of them everywhere, and the leak check fails if any survives. |
| `registry.json` | Every person and organization found, with their stable pseudonym (`[PERSON-03]`). |
| `cache/` | Cached text extraction, OCR and local-LLM results, so reruns take seconds. |
| `staging/` | Output before the leak check. Published to `filtered/` only when the check passes. |
| `review/index.html` | The original text with every redaction highlighted. **Open it in your browser and check it**: red = names, blue = organizations, yellow = other identifiers. |
| `verify_report.md` | Leak-check hits with their context. |
| `audit_suspects.md`, `identifier_inventory.md` | Word lists from `pipeline audit` and `pipeline ids`, for you to review. |
| `accepted_warnings.json` | Leak-check warnings you reviewed and accepted (`run --accept-warnings`). |

Back this folder up with the same care as the records themselves. Deleting `cache/` only makes the next run slow.
