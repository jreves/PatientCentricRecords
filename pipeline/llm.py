"""Local LLM identifier detection through Ollama. Results are cached under private/."""
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

PROMPT_VERSION = 1

TYPE_MAP = {"PATIENT_NAME": "PATIENT", "CLINICIAN_NAME": "CLINICIAN", "OTHER_PERSON_NAME": "PERSON",
            "ORGANIZATION": "FACILITY", "ADDRESS": "ADDRESS", "PHONE_FAX": "PHONE", "EMAIL": "EMAIL",
            "URL": "URL", "ID_NUMBER": "ID"}

SCHEMA = {"type": "object", "required": ["entities"], "properties": {"entities": {"type": "array", "items": {
    "type": "object", "required": ["text", "type"], "properties": {
        "text": {"type": "string"}, "type": {"type": "string", "enum": list(TYPE_MAP)}}}}}}

PROMPT = """You are a HIPAA de-identification tool. Extract every personal identifier from the clinical text below.

Include:
- names of people: the patient, clinicians and staff, family members, other contacts
- names of hospitals, clinics, practices, labs, pharmacies, insurers and other organizations
- street addresses, and cities or towns
- phone and fax numbers, email addresses, URLs
- medical record, account, accession, specimen, insurance or other ID numbers

Exclude: drugs, diseases, procedures, tests, lab values, biomarkers, genes, clinical trial names, anatomy,
dates, ages, and generic roles such as "patient" or "oncologist".

Copy each identifier exactly as it is written in the text, character for character. List each distinct identifier once.

TEXT:
"""


class LLMError(RuntimeError):
    pass


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def require_local(url):
    """Raw clinical text is sent to this URL: refuse anything that is not this machine."""
    host = urllib.parse.urlsplit(url).hostname
    if host not in LOCAL_HOSTS:
        raise LLMError(f"llm.url must point at this machine (localhost), not {host!r}: raw text is sent to it.")
    return url.rstrip("/")


class OllamaNER:
    def __init__(self, cfg, cache_dir):
        self.base = require_local(cfg["url"])
        self.model = cfg["model"]
        self.think = cfg.get("think", False)
        self.num_ctx = cfg.get("num_ctx", 8192)
        self.timeout = cfg.get("timeout_s", 900)
        self.max_chars = cfg.get("max_chunk_chars", 3500)
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls = self.cache_hits = self.failures = 0
        self.checked = False   # Ollama is only contacted when a chunk is not in the cache

    def check(self):
        self.checked = True
        try:
            with urllib.request.urlopen(self.base + "/api/tags", timeout=10) as r:
                names = {m["name"] for m in json.loads(r.read())["models"]}
        except (urllib.error.URLError, OSError):
            raise LLMError(f"Ollama is not reachable at {self.base}. Start the Ollama tray app "
                           "(not `ollama serve` from a shell: that instance may not see the GPU).") from None
        if self.model not in names:
            raise LLMError(f"Model {self.model} is not pulled. Run: ollama pull {self.model} (or see `python -m pipeline doctor` for a model that suits this machine)")

    def detect(self, text):
        """Return [(surface, cat)] or None if any chunk could not be processed."""
        out = []
        for chunk in self._chunks(text):
            ents = self._detect_chunk(chunk, depth=0)
            if ents is None:
                self.failures += 1
                return None
            out += ents
        return out

    def _lines(self, text):
        """Lines, with any line longer than a chunk split at cell (' | ') or word boundaries.
        A 4.7k-character table line once made the model's JSON overflow (2026-09-27)."""
        limit = self.max_chars // 2
        for line in text.split("\n"):
            while len(line) > limit:
                cut = line.rfind(" | ", 0, limit)
                cut = cut if cut > 0 else line.rfind(" ", 0, limit)
                cut = cut if cut > 0 else limit
                yield line[:cut]
                line = line[cut:].lstrip(" |")
            yield line

    def _chunks(self, text):
        chunk, size = [], 0
        for line in self._lines(text):
            if size + len(line) > self.max_chars and chunk:
                yield "\n".join(chunk)
                chunk, size = [], 0
            chunk.append(line)
            size += len(line) + 1
        if chunk:
            yield "\n".join(chunk)

    def _detect_chunk(self, chunk, depth):
        if not chunk.strip():
            return []
        key = hashlib.sha256(f"{PROMPT_VERSION}|{self.model}|{chunk}".encode()).hexdigest()
        cached = self.cache_dir / f"{key}.json"
        if cached.exists():
            self.cache_hits += 1
            return [tuple(e) for e in json.loads(cached.read_text(encoding="utf-8"))]
        if not self.checked:
            self.check()
        ents = self._call(chunk)
        if ents is None:
            if depth >= 2 or len(chunk) < 400:
                return None
            # Retry on halves: long or unusual chunks sometimes yield truncated JSON.
            lines = chunk.split("\n")
            mid = max(1, len(lines) // 2)
            parts = ["\n".join(lines[:mid]), "\n".join(lines[mid:])]
            results = [self._detect_chunk(p, depth + 1) for p in parts]
            if any(r is None for r in results):
                return None
            merged = results[0] + results[1]
            # Cache the combined answer under the original chunk too: otherwise every run re-asks the model
            # for it, waits for the failure (up to num_predict tokens), then splits again (2026-09-28).
            cached.write_text(json.dumps(merged), encoding="utf-8")
            return merged
        cached.write_text(json.dumps(ents), encoding="utf-8")
        return ents

    def _call(self, chunk):
        body = {"model": self.model, "stream": False, "think": self.think, "format": SCHEMA,
                "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": 2048},
                "messages": [{"role": "user", "content": PROMPT + chunk}]}
        req = urllib.request.Request(self.base + "/api/chat", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        self.calls += 1
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                content = json.loads(r.read())["message"]["content"]
            ents = json.loads(content)["entities"]
        except (urllib.error.URLError, OSError) as e:
            raise LLMError(f"Ollama request failed: {type(e).__name__}") from None
        except (ValueError, KeyError, TypeError):
            return None  # never echo model output: it contains raw PII
        return [(e["text"], TYPE_MAP[e["type"]]) for e in ents
                if isinstance(e, dict) and isinstance(e.get("text"), str) and e.get("type") in TYPE_MAP]
