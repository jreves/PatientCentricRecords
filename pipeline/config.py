"""Paths and configuration loading."""
import os
import pathlib
import tomllib
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent
PIPELINE_VERSION = "0.8.3"


@dataclass
class Paths:
    root: pathlib.Path      # base for relative source paths
    private: pathlib.Path   # raw-PII working area: never read by Claude, never committed
    output: pathlib.Path    # published, de-identified notes

    @property
    def staging(self): return self.private / "staging"
    @property
    def cache(self): return self.private / "cache" / "llm"
    @property
    def registry(self): return self.private / "registry.json"
    @property
    def review(self): return self.private / "review"
    @property
    def identifiers(self): return self.private / "identifiers.toml"


LIST_MERGE = {("allowlist", "terms"), ("allowlist", "no_bare_match")}   # local entries are added to the shared defaults


def merge_config(base, local):
    """Overlay a local config on the shared one: tables merge key by key, [[sources]] is replaced,
    allowlist terms and no_bare_match are concatenated."""
    out = dict(base)
    for k, v in local.items():
        if k == "sources":
            out[k] = v
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            t = dict(out[k])
            for kk, vv in v.items():
                t[kk] = (t.get(kk, []) + [x for x in vv if x not in t.get(kk, [])]) if (k, kk) in LIST_MERGE else vv
            out[k] = t
        else:
            out[k] = v
    return out


def load_config(path=None, local=None):
    """config/pipeline.toml (shared defaults, committed) overlaid with config/local.toml (this machine's sources and
    tuning: git-ignored, because allowlist words and source names can reveal where a patient was treated)."""
    path = pathlib.Path(path or ROOT / "config" / "pipeline.toml")
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    local = pathlib.Path(local or os.environ.get("PCR_LOCAL_CONFIG") or ROOT / "config" / "local.toml")
    if local.exists():
        cfg = merge_config(cfg, tomllib.loads(local.read_text(encoding="utf-8")))
    return cfg


def default_paths(cfg):
    return Paths(ROOT, ROOT / "private", ROOT / cfg["output"]["dir"])


def load_identifiers(paths):
    if not paths.identifiers.exists():
        return {}
    return tomllib.loads(paths.identifiers.read_text(encoding="utf-8"))


def long_path(p):
    """On Windows, the extended-length form of a path (portal filenames can exceed MAX_PATH); elsewhere, the path itself."""
    s = str(pathlib.Path(p).resolve())
    if os.name != "nt":
        return s
    return s if s.startswith("\\\\?\\") else "\\\\?\\" + s
