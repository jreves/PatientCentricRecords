"""A patient's case file: the facts the reports are drawn from.

The case lives outside the repository (default ``analysis/case/``, git-ignored) as one or more YAML files that are merged
in name order, plus the narrative ``document.html`` for the full timeline. Claude (or the user) writes these from the
published, de-identified notes in ``filtered/`` -- never from the raw sources. See docs/case-file.md for the schema.

Values may use ``@today`` for "the build date", so ongoing treatments extend automatically.
"""
import os
import pathlib
import re
from datetime import date

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _config():
    """The pipeline's configuration (shared defaults with config/local.toml merged over them)."""
    from pipeline.config import load_config
    try:
        return load_config()
    except FileNotFoundError:
        return {}


def _resolve(obj, today):
    """``@today`` -> the case's today; YAML dates (unquoted 2026-01-31) -> ISO strings, as the reports expect."""
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, str):
        return today if obj == "@today" else obj
    if isinstance(obj, list):
        return [_resolve(x, today) for x in obj]
    if isinstance(obj, dict):
        return {k: _resolve(v, today) for k, v in obj.items()}
    return obj


class Case(dict):
    def __init__(self, path):
        self.dir = pathlib.Path(path).resolve()
        if not self.dir.is_dir():
            raise SystemExit(f"No case directory at {self.dir}. Create one (see docs/case-file.md or examples/case/).")
        data = {}
        for f in sorted(self.dir.glob("*.yaml")):
            part = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            for k, v in part.items():
                if k in data and isinstance(data[k], dict) and isinstance(v, dict):
                    data[k].update(v)
                else:
                    data[k] = v
        today = _resolve(data.get("dates", {}).get("today"), None)
        super().__init__(_resolve(data, today))
        d = self["dates"]
        self.today, self.built, self.records_through = str(d["today"]), str(d["built"]), str(d["records_through"])
        p = self.get("patient", {})
        self.summary = p.get("summary", "")
        self.disclaimer = p.get("disclaimer", "").format(records_through=self.records_through)
        self.disclaimer_full = self.disclaimer + (" " + p["disclaimer_tail"] if p.get("disclaimer_tail") else "")
        # The published notes the lab, vitals and medication reports read: $PCR_NOTES, else the case's ``notes_dir``
        # (relative to the case folder), else the pipeline's output. A case for another patient must set notes_dir.
        if os.environ.get("PCR_NOTES"):
            self.notes = pathlib.Path(os.environ["PCR_NOTES"])
        elif self.get("notes_dir"):
            self.notes = (self.dir / self["notes_dir"]).resolve()
        else:
            self.notes = ROOT / _config().get("output", {}).get("dir", "filtered") / "notes"
        self.marker = self._marker()

    def _marker(self):
        """[(iso date, value)] for the tumour marker, from a published spreadsheet note or listed values."""
        m = self.get("tumor_marker")
        if not m:
            return []
        vals = [(str(d), float(v)) for d, v in m.get("values", [])]
        src = m.get("source")
        if src:
            f = next(self.notes.glob(src["glob"]), None)
            if f:
                vals += [(d, float(v)) for d, v in re.findall(src["pattern"], f.read_text(encoding="utf-8"), re.M)]
        return sorted(set(vals))

    def text(self, key, **kw):
        """A prose fragment from the case (``texts:`` section), with {built}/{today}/... filled in."""
        t = self["texts"][key]
        return t.format(built=self.built, today=self.today, records_through=self.records_through, summary=self.summary, **kw) if kw or "{" in t else t


_CASE = None


def load(path=None):
    global _CASE
    if _CASE is None or path:
        _CASE = Case(path or os.environ.get("PCR_CASE") or ROOT / "analysis" / "case")
    return _CASE
