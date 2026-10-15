"""Name parsing, the persistent pseudonym registry, and name-variant search patterns.

The registry (private/registry.json) maps every detected person and organization to a
stable pseudonym such as [CLINICIAN-03], so the same clinician keeps the same token
across notes and across runs. It holds raw names and must stay private.
"""
import json
import pathlib
import re
from collections import Counter, defaultdict

TITLES = {"dr", "doctor", "mr", "mrs", "ms", "miss", "mx", "prof"}
FEMALE_TITLES = {"ms", "mrs", "miss"}
CREDS = {"md", "do", "np", "rn", "lpn", "pa", "pa-c", "phd", "ph", "facs", "facp", "aprn", "fnp", "fnp-c", "fnp-bc",
         "anp", "anp-bc", "agpcnp-bc", "cnp", "crnp", "dnp", "msn", "bsn", "pharmd", "rph", "bcop", "crna", "mph",
         "lcsw", "rd", "ld", "cns", "ocn", "aocnp", "aocns", "whnp", "facog", "mba", "jr", "sr", "ii", "iii", "iv",
         "mbbs", "frcpc", "cma"}
# Words that detectors sometimes capture as names but never are.
GENERIC = {"nurse", "practitioner", "physician", "doctor", "provider", "patient", "oncology", "oncologist",
           "medical", "center", "clinic", "hospital", "health", "care", "cancer", "breast", "radiology",
           "pathology", "surgery", "department", "unknown", "none", "self", "other", "staff", "team", "office",
           "attending", "resident", "fellow", "family", "husband", "wife", "daughter", "son", "mother", "father",
           "sister", "brother", "spouse", "pt", "she", "he", "her", "his", "n/a", "na", "the", "and", "of",
           # labels and clinical abbreviations that land next to names in headers
           "id", "mrn", "dob", "dos", "acct", "fax", "phone", "age", "sex", "er", "pr", "ct", "pet", "mri", "cc",
           "ed", "icu", "or", "pcp", "npi", "csn", "fin", "her2", "ki", "dx", "tx", "hx", "rx", "sx",
           "am", "pm"}   # "2:50 AM MDT" was read as a name (2026-09-26)
ORG_WORDS = {"hospital", "center", "centre", "clinic", "oncology", "medical", "health", "healthcare", "institute",
             "university", "associates", "imaging", "radiology", "laboratory", "laboratories", "lab", "labs",
             "group", "cancer", "care", "pharmacy", "baptist", "methodist", "memorial", "regional", "surgery",
             "surgical", "partners", "physicians", "services", "specialists", "system", "network", "foundation",
             "diagnostics", "consultants", "practice", "infusion", "insurance", "medicare", "medicaid"}

WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
TITLE_PREFIX = re.compile(r"^(?:Dr|Doctor|Mr|Mrs|Ms|Miss|Mx|Prof)\.?\s+", re.I)
FLAGS_CI = re.I


def _is_cred(word):
    w = word.replace(".", "").lower()
    return w in CREDS and (word.isupper() or w in {"phd", "pharmd", "ph"})


def parse_name(surface):
    """-> (first|None, last, title|None) in lowercase, or None if not a usable name."""
    s = re.sub(r"\(.*?\)", " ", surface).strip()
    title = None
    m = TITLE_PREFIX.match(s)
    if m:
        title = m.group(0).strip().rstrip(".").lower()
        s = s[m.end():]
    parts = []
    for part in s.split(","):
        words = [w for w in WORD.findall(part)
                 if len(w) > 1 and not _is_cred(w) and w.lower() not in TITLES]
        if words:
            parts.append(words)
    if not parts:
        return None
    words = parts[1] + parts[0] if len(parts) >= 2 else parts[0]   # "Last, First" -> First ... Last
    words = [w.lower() for w in words]
    last = words[-1]
    first = words[0] if len(words) > 1 else None
    if last in GENERIC:
        return None
    if first in GENERIC:
        first = None
    return first, last, title


def trim_name_span(text, s, e):
    """Drop a leading title and trailing credentials/possessive so they stay readable."""
    m = TITLE_PREFIX.match(text[s:e])
    if m:
        s += m.end()
    while True:
        seg = text[s:e]
        if seg.endswith("'s"):
            e -= 2
            continue
        m = re.search(r"[,\s]+([A-Za-z.\-]+)\s*$", seg)
        if m and _is_cred(m.group(1)):
            e = s + m.start()
            continue
        break
    seg = text[s:e]
    e -= len(seg) - len(seg.rstrip(" ,.\t"))
    return s, e


def norm(surface):
    return re.sub(r"[^a-z0-9]+", " ", surface.lower()).strip()


def _compatible(a, b):
    return a == b or (a and b and a[0] == b[0] and (len(a) == 1 or len(b) == 1))


class Registry:
    def __init__(self, path):
        self.path = path
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        # entity: {id, cat, names: [[first|null, last]], aliases: [str], surfaces: [str]}
        self.entities = data.get("entities", [])
        self.orgs = data.get("orgs", [])          # {id, key, surfaces}
        self.counters = Counter(data.get("counters", {}))
        self._hints = defaultdict(Counter)        # entity index -> category votes (this run)
        self._reindex()

    def _reindex(self):
        """Lookup indexes and a resolve() memo. Scanning and re-sorting ~800 entities for each of tens of
        thousands of spans made a cached run take >10 minutes (2026-09-28)."""
        self._by_last, self._by_first = defaultdict(list), defaultdict(list)
        self._org_by_key = {o["key"]: o for o in self.orgs}
        self._patient = next((e for e in self.entities if e["id"] == "PATIENT"), None)
        self._memo = {}
        for e in self.entities:
            self._index(e)

    def _index(self, e):
        for f, l in e["names"]:
            if e not in self._by_last[l]:
                self._by_last[l].append(e)
            if f and e not in self._by_first[f]:
                self._by_first[f].append(e)
        for a in e.get("aliases", []):
            if e not in self._by_first[a]:
                self._by_first[a].append(e)
        self._memo = {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entities": self.entities, "orgs": self.orgs, "counters": dict(self.counters)}
        self.path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    # --- lookup -----------------------------------------------------------------
    @property
    def patient(self):
        return self._patient

    def _match_full(self, first, last):
        for e in sorted(self._by_last.get(last, []), key=lambda e: e["id"] != "PATIENT"):
            for f, l in e["names"]:
                if l == last and _compatible(f, first):
                    return e
        return None

    def _match_single(self, tok, hint, title):
        by_last = list(self._by_last.get(tok, []))
        by_first = list(self._by_first.get(tok, []))
        pat = self.patient
        if pat in by_last and (hint == "PATIENT" or title in FEMALE_TITLES or len(by_last) == 1):
            return pat
        if pat in by_first and hint != "CLINICIAN" and title != "dr":
            return pat
        if hint == "CLINICIAN" or title == "dr":
            clin = [e for e in by_last if e["cat"] == "CLINICIAN"]
            if len(clin) == 1:
                return clin[0]
        for group in (by_last, by_first):
            if len(group) == 1:
                return group[0]
        if by_last:
            return pat if pat in by_last else by_last[0]
        return None

    def resolve(self, surface, hint):
        key = (surface, hint)
        if key in self._memo:
            return self._memo[key]
        parsed = parse_name(surface)
        if not parsed:
            result = None
        else:
            first, last, title = parsed
            result = self._match_full(first, last) if first else self._match_single(last, hint, title)
        self._memo[key] = result
        return result

    def token(self, entity):
        return "[PATIENT]" if entity["id"] == "PATIENT" else f"[{entity['id']}]"

    def org_for(self, surface):
        return self._org_by_key.get(norm(surface))

    # --- build ------------------------------------------------------------------
    def _new(self, cat, names, aliases=()):
        e = {"id": None, "cat": cat, "names": [list(n) for n in names], "aliases": list(aliases), "surfaces": []}
        self.entities.append(e)
        self._index(e)
        return e

    def _vote(self, e, hint, surface):
        self._hints[id(e)][hint] += 1
        if surface not in e["surfaces"]:
            e["surfaces"].append(surface)

    def build(self, mentions, identifiers, allow):
        """mentions: [(surface, hint)] where hint is PATIENT/CLINICIAN/PERSON/FACILITY."""
        pinfo = identifiers.get("patient", {})
        pat = self.patient
        seeded = [parse_name(n) for n in pinfo.get("names", [])]
        seeded = [(f, l) for f, l, _ in filter(None, seeded)]
        nick = [n.lower() for n in pinfo.get("nicknames", [])]
        if seeded:
            if pat is None:
                pat = self._new("PATIENT", [], [])
                pat["id"] = "PATIENT"
                self._reindex()
            for n in seeded:
                if list(n) not in pat["names"]:
                    pat["names"].append(list(n))
            pat["aliases"] = sorted(set(pat["aliases"]) | set(nick))
            self._reindex()
        for person in identifiers.get("people", {}).get("names", []):
            parsed = parse_name(person)
            if parsed:
                e = self.resolve(person, "PERSON") or self._new("PERSON", [parsed[:2]])
                e["pinned"] = True   # user-listed: always a redacted person, whatever the detectors say

        people = [(s, h) for s, h in mentions if h != "FACILITY" and not allow.blocks(s)]
        full = [(s, h, p) for s, h in people if (p := parse_name(s)) and p[0]]
        single = [(s, h, p) for s, h in people if (p := parse_name(s)) and not p[0]]

        if self.patient is None:
            # No identifiers given: the full name the LLM most often calls "patient" is the patient.
            votes = Counter((p[0], p[1]) for s, h, p in full if h == "PATIENT")
            if votes:
                pat = self._new("PATIENT", [votes.most_common(1)[0][0]])
                pat["id"] = "PATIENT"
                self._reindex()

        for s, h, (f, l, _) in sorted(full, key=lambda x: -len(x[0])):
            e = self._match_full(f, l) or self._new(h, [(f, l)])
            self._vote(e, h, s)
        for s, h, (_, tok, title) in single:
            e = self._match_single(tok, h, title) or self._new(h, [(None, tok)])
            self._vote(e, h, s)

        for s, h in mentions:
            if h != "FACILITY" or allow.blocks(s):
                continue
            words = norm(s).split()
            if not words or all(w in ORG_WORDS or w in GENERIC for w in words):
                continue
            if len(words) <= 2 and not any(w in ORG_WORDS for w in words):
                e = self.resolve(s, "PERSON")   # e.g. a family member's first name mislabeled as an org
                if e:
                    self._vote(e, "PERSON", s)
                    continue
            o = self.org_for(s)
            if o is None:
                o = {"id": None, "key": norm(s), "surfaces": []}
                self.orgs.append(o)
                self._org_by_key[o["key"]] = o
            if s not in o["surfaces"]:
                o["surfaces"].append(s)

        self._prune(allow)
        self._assign_ids()
        self._reindex()

    def _prune(self, allow):
        """Drop non-name entities: not detected in this run (stale, e.g. from an earlier
        buggy run), every part a known medical term, or only ever seen in lowercase (real
        names are capitalized). User-listed people and the patient always stay. Ids of
        surviving entities never change, and counters only grow, so tokens stay stable."""
        def junk(e):
            if e["id"] == "PATIENT" or e.get("pinned"):
                return False
            if not self._hints.get(id(e)):
                return True
            parts = [p for f, l in e["names"] for p in (f, l) if p]
            if parts and all(allow.bare_blocked(p) for p in parts):
                return True
            return bool(e["surfaces"]) and not any(any(c.isupper() for c in s) for s in e["surfaces"])
        self.entities = [e for e in self.entities if not junk(e)]
        self.orgs = [o for o in self.orgs if not all(allow.blocks(s) for s in o["surfaces"])]

    def _assign_ids(self):
        """Decide CLINICIAN vs PERSON each run. Clinician names may be published, so the
        rules lean towards PERSON: user-listed people and anyone sharing the patient's
        surname are always PERSON, and a tie in the votes is PERSON."""
        pat = self.patient
        family = {l for _, l in pat["names"]} if pat else set()
        for e in self.entities:
            if e["id"] == "PATIENT":
                continue
            votes = self._hints.get(id(e), Counter())
            votes.pop("PATIENT", None)
            if e.get("pinned") or any(l in family for _, l in e["names"]):
                cat = "PERSON"
            elif votes:
                cat = "CLINICIAN" if votes["CLINICIAN"] > votes["PERSON"] else "PERSON"
            else:
                cat = "CLINICIAN" if e["cat"] == "CLINICIAN" else "PERSON"
            if e["id"] is None or not e["id"].startswith(cat + "-"):
                self.counters[cat] += 1
                e["id"] = f"{cat}-{self.counters[cat]:02}"
            e["cat"] = cat
            if votes:
                e["votes"] = dict(votes)   # kept for shape-only diagnostics
        for o in self.orgs:
            if o["id"] is None:
                self.counters["FACILITY"] += 1
                o["id"] = f"FACILITY-{self.counters['FACILITY']:02}"

    # --- search patterns ----------------------------------------------------------
    def patterns(self, allow):
        """[(regex, token, cat, require_capital)] finding every known variant of every name."""
        out = []
        bound = lambda body: re.compile(rf"(?<![A-Za-z]){body}(?![A-Za-z])", FLAGS_CI)
        for e in self.entities:
            tok, cat = self.token(e), e["cat"]
            singles = set(e.get("aliases", []))
            for f, l in e["names"]:
                L = re.escape(l)
                if f:
                    F = re.escape(f)
                    out.append((bound(rf"{F}(?:[ \t]+(?:[A-Z]\.?|[A-Z][a-z]+))?[ \t]+{L}"), tok, cat, False))
                    out.append((bound(rf"{L},[ \t]*{F}(?:[ \t]+[A-Z]\.?(?![a-zA-Z]))?"), tok, cat, False))
                    if cat != "CLINICIAN":
                        singles.add(f)
                singles.add(l)
            for w in singles:
                if len(w) >= 3 and w not in GENERIC and not allow.bare_blocked(w):
                    out.append((bound(re.escape(w)), tok, cat, True))
        for o in self.orgs:
            for s in o["surfaces"]:
                body = r"\s+".join(re.escape(w) for w in s.split())
                out.append((bound(body), f"[{o['id']}]", "FACILITY", False))
        # Longer patterns first so full names win over their parts.
        out.sort(key=lambda p: -len(p[0].pattern))
        return out

    def known_surfaces(self):
        """Every raw name string seen, for the leak check."""
        for e in self.entities:
            yield from ((s, e["cat"]) for s in e["surfaces"])
        for o in self.orgs:
            yield from ((s, "FACILITY") for s in o["surfaces"])


DOSE_WORDS = {"mg", "mcg", "ml", "tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "daily", "bid", "tid",
              "qd", "prn", "iv", "po", "sq", "units", "dose", "doses", "cycle", "cycles", "weekly"}
MEDICAL_TERMS = pathlib.Path(__file__).resolve().parent.parent / "config" / "medical_terms.txt"
LOCAL_TERMS = MEDICAL_TERMS.with_name("medical_terms.local.txt")   # this machine's additions (git-ignored)


def load_medical_terms(path=MEDICAL_TERMS, local=LOCAL_TERMS):
    out = set()
    for p in (path, local):
        if p and p.exists():
            lines = p.read_text(encoding="utf-8").splitlines()
            out |= {norm(line) for line in lines if line.strip() and not line.lstrip().startswith("#")}
    return out


class Allowlist:
    """Surfaces that are never names: config allowlist + config/medical_terms.txt."""

    def __init__(self, cfg):
        a = cfg.get("allowlist", {})
        self.terms = {norm(t) for t in a.get("terms", [])} | load_medical_terms()
        self.bare = {norm(t) for t in a.get("no_bare_match", [])}
        self.term_words = {w for t in self.terms if " " in t for w in t.split()
                           if re.search(r"[a-z]{3}", w) and w not in DOSE_WORDS}

    def blocks(self, surface):
        n = norm(surface)
        if n in self.terms:
            return True
        # "Femara 2.5", "Ibrance 125 mg", "Tempus xT": known terms plus doses or short tokens.
        # Words of multi-word entries count too, so "Lidocaine-Prilocaine" matches the entry
        # "Lidocaine-Prilocaine Topical Cream". A term beside any other real word ("Jane Caris")
        # could be a name that shares a drug's spelling, so it is not exempt.
        words = [norm(w) for w in surface.replace("-", " ").replace("/", " ").split()]
        real = [w for w in words if re.search(r"[a-z]{3}", w) and w not in DOSE_WORDS]
        return bool(real) and all(w in self.terms or w in self.term_words for w in real)

    def bare_blocked(self, word):
        return norm(word) in self.bare or norm(word) in self.terms
