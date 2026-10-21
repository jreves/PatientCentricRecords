# The source audit

Before handing the reports to a new physician, the family should be able to answer: *where does each statement come
from?* The source audit answers that for every statement, every time the reports are built.

![First page of a source audit](images/source-audit.png)

## What it checks

Every statement in the reports comes from the case file: each treatment, date, dose, scan, procedure, side effect,
emergency-card line and narrative paragraph. Each one must cite its source in `analysis/case/citations.yaml`. A source
is one of:
- a **record note** and a **quote** copied word for word from it;
- a **family report**: something the family knows that the records don't contain, such as who gave a treatment
  decades ago;
- a **search**: for a statement that something is *not* in the records, all published notes are searched to
  confirm it.

The audit then runs three checks, all on your computer:

1. **The citation is real.** The note exists, and the quote is in it word for word (spacing and line breaks aside).
2. **The details match.** Every date, dose or measurement (`20 Gy`, `85%`, `1.4 cm`), drug or test name and
   clinician named in the statement must appear in the cited notes. Dates count in any format, so 3/23/2024,
   03/23/24 and 2024-03-23 are the same date. Brand and generic drug names count as the same drug.
3. **The meaning holds.** The local model reads the statement next to the cited passages and judges each fact
   separately: supported or not. This is a second opinion, not proof. It catches a real quote cited for the wrong
   fact, which checks 1 and 2 can't.

## Reading the appendix

The first lines give the bottom line: how many statements are grounded, how many rest on family reports, and how
many need attention. Then each statement is listed with:

| Column | What it shows |
|---|---|
| **Status** | Citation problem · Partly grounded · No source yet · Family report · Grounded |
| **Claim** | the statement as the reports print it |
| **Source note and quote** | each cited note's id, date and type, and the quote. A note marked *authoritative* outranks the rest for what it covers; the family's current medication list is one. |
| **Checks** | the model's verdict (*supported*, or *partly supported* with the facts it doubted), details not found, anything accepted by hand, and **Reviewed by hand** notes |

Statements that need attention come first. Within each status, sections follow a physician's reading order:
treatments, doses, side effects, pathology, imaging, events, then the emergency card, charts and narrative.

## What to do with each status

| Status | Meaning | What to do |
|---|---|---|
| **Citation problem** | the cited note doesn't exist, the quote isn't in it, or a "not in the records" search found matches | fix the citation. If a search found matches, the statement is wrong: the records *do* mention it, so correct the wording. |
| **Partly grounded** | a date, dose, drug or clinician in the statement isn't in the cited notes | cite another note that has it, or correct the statement. Only if the family confirms it, accept it with a reason. |
| **No source yet** | nothing cited | find the note that says it (`python -m reports audit --suggest` proposes candidates to review) |
| **Family report** | the family supplied it | nothing, as long as it's right. It's listed so a physician can tell family knowledge from documented fact. |
| **Grounded** | citation and details check out | nothing. If the model doubted it, there should be a "Reviewed by hand" note saying what was checked. |

## When the model doubts a statement

The model is careful but not always right. It sometimes misses a fact that's plainly in a passage, or doubts
everything in a long statement because one part isn't shown. For each doubted statement:

1. Look at the cited passages yourself. Ask Claude Code to show where each doubted fact is in the cited notes.
2. If the fact is there, add a `reviewed:` note to the citation saying where, for example
   *"'2000 cGy/5 fx' in the 1/17/2023 history"*.
3. If it isn't there, cite the note that does have it, or correct the statement.

## Errors the audit has caught

From real use, with details removed:
- A "not documented anywhere in the records" statement was **contradicted** by the search: two dozen notes mentioned
  it.
- A quote attributed to one visit was really from another visit, and that visit's note said the opposite.
- A test was described as done during one drug when, by the case's own timeline, the patient was on another.
- Facts the family had reported, such as vaccines given at a pharmacy, later appeared in a record. The citation then
  moved from "family report" to the record.

## Commands

```bash
python -m reports build              # builds the reports, then runs the audit (warns, never stops the build)
python -m reports audit              # just the audit
python -m reports audit --suggest    # propose citations for unsourced statements (citations.suggested.yaml)
python -m reports audit --no-semantic   # skip the model's reading (fast; checks 1 and 2 only)
```

The model's answers are cached, so a rebuild re-checks only statements or citations that changed. The format of
`citations.yaml` is in [case-file.md](case-file.md#citations-and-the-source-audit-citationsyaml).
