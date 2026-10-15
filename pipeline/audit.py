"""Count-only audit of redacted PERSON entities in the published output.

Flags likely false positives (drug names, ordinary words) without printing any name
or note text: only token ids, counts, letter-case patterns and letter-masked contexts
(A = capital, a = lowercase, 9 = digit, [T] = any token). Safe for hosted Claude to read.
"""
import collections
import re

from .names import Registry

TOKEN = re.compile(r"\[[A-Z]+(?:-\d+)?(?:; age [\d+]+)?\]")


def shape(s):
    parts, pos = [], 0
    for m in TOKEN.finditer(s):
        parts += [re.sub(r"[a-z]", "a", re.sub(r"[A-Z]", "A", re.sub(r"\d", "9", s[pos:m.start()]))), "[T]"]
        pos = m.end()
    parts.append(re.sub(r"[a-z]", "a", re.sub(r"[A-Z]", "A", re.sub(r"\d", "9", s[pos:]))))
    return "".join(parts).replace("\n", "|")


KINDS = ["PERSON_NAME", "MEDICATION", "LAB_OR_TEST", "ORGANIZATION_OR_PLACE", "OTHER_CLINICAL_TERM"]
CLASSIFY_PROMPT = """In these excerpts from a clinical note, the term shown as <<TERM>> was flagged as a possible
personal name. Decide what the term actually is. A medication includes brand and generic drug names and
supplements. A lab or test includes assays, panels, scans, scores and scales.

Term: {term}

Excerpts:
{excerpts}
"""


def classify_locally(cfg_llm, term, excerpts):
    """Ask the LOCAL model what a redacted term is. The term never leaves this machine."""
    import json
    import urllib.request
    body = {"model": cfg_llm["model"], "stream": False, "think": cfg_llm.get("think", False),
            "format": {"type": "object", "required": ["kind"],
                       "properties": {"kind": {"type": "string", "enum": KINDS}}},
            "options": {"temperature": 0, "num_ctx": 4096},
            "messages": [{"role": "user", "content": CLASSIFY_PROMPT.format(
                term=term, excerpts="\n".join(f"- {x}" for x in excerpts))}]}
    req = urllib.request.Request(cfg_llm["url"].rstrip("/") + "/api/chat", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=cfg_llm.get("timeout_s", 600)) as r:
            return json.loads(json.loads(r.read())["message"]["content"])["kind"]
    except Exception:  # never surface model output or text in errors
        return "UNKNOWN"


def audit(paths, cfg=None, log=print, min_uses=5):
    registry = Registry(paths.registry)
    classify = cfg is not None and cfg.get("llm", {}).get("enabled", True)
    private_rows = []
    text = "\n".join(p.read_text(encoding="utf-8") for p in sorted((paths.output / "notes").glob("*.md")))
    rows = []
    for e in registry.entities:
        if e["cat"] != "PERSON":
            continue
        tok = registry.token(e)
        uses = [m.start() for m in re.finditer(re.escape(tok), text)]
        if not uses:
            continue
        listed = len(uses) >= min_uses   # console rows; the private file lists every entity
        full = any(f for f, _ in e["names"])
        # Propagation only redacts capitalized forms, so lowercase uses survive in the output.
        lower = 0 if full else len(re.findall(rf"(?<![A-Za-z]){re.escape(e['names'][0][1])}(?![A-Za-z])", text))
        line_start = sum(1 for u in uses if u == 0 or text[u - 1] == "\n") * 100 // len(uses)
        ctx = collections.Counter(shape(text[max(0, u - 14):u]) + "<T>" + shape(text[u + len(tok):u + len(tok) + 14])
                                  for u in uses).most_common(1)[0]
        suspect = []
        if lower:
            suspect.append("also used as a lowercase word")
        if not full and len(uses) >= 40:
            suspect.append("single word used very often")
        kind = ""
        if classify and not e.get("pinned"):
            surface = max(e["surfaces"], key=len) if e["surfaces"] else e["names"][0][1]
            excerpts = [text[max(0, u - 80):u].replace("\n", " ") + f"<<{surface}>>"
                        + text[u + len(tok):u + len(tok) + 80].replace("\n", " ") for u in uses[:3]]
            kind = classify_locally(cfg["llm"], surface, excerpts)
            private_rows.append((e["id"], len(uses), kind, surface))
            if kind not in ("PERSON_NAME", "UNKNOWN"):
                suspect.append(f"local model says {kind}")
        if listed:
            rows.append((len(uses), e["id"], full, lower, line_start, ctx, suspect, e.get("votes"), bool(e.get("pinned"))))
    others = [r for r in private_rows if r[1] < min_uses]
    log(f"PERSON entities with >= {min_uses} uses in published notes: {len(rows)} "
        f"(+{len(others)} rarer ones, of which {sum(1 for r in others if r[2] not in ('PERSON_NAME', 'UNKNOWN'))} "
        f"the local model calls non-names; all are in the private file)")
    for n, eid, full, lower, ls, ctx, suspect, votes, pinned in sorted(rows, reverse=True):
        flag = "SUSPECT: " + "; ".join(suspect) if suspect else ""
        log(f"  {eid:<10} uses {n:>4} | {'full name' if full else 'one word'} | lowercase {lower:>3} | "
            f"line-start {ls:>3}% | votes {votes} {'pinned' if pinned else ''} | {ctx[1]}x '{ctx[0]}' {flag}")
    if private_rows:
        report = paths.private / "audit_suspects.md"
        lines = ["# Audit: redacted 'people' (PRIVATE: contains the redacted words)", "",
                 "The local model's guess at what each redacted term is. For every row that is NOT a",
                 "person, add the term to config/medical_terms.txt, then rerun `python -m pipeline run`.", "",
                 "| Token | Uses | Local model says | Term |", "|---|---|---|---|"]
        lines += [f"| {i} | {n} | {k} | {s} |" for i, n, k, s in sorted(private_rows, key=lambda r: -r[1])]
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log(f"Wrote private/audit_suspects.md ({len(private_rows)} rows) for the USER to review.")
    log("Check SUSPECT ids in private/audit_suspects.md or private/review/*.html. If a term is not a person,\n"
        "add it to config/medical_terms.txt and rerun.")
