"""CLI: python -m pipeline {init,run,verify,audit,ids,doctor}"""
import argparse
import pathlib
import shutil
import sys

from .config import ROOT, default_paths, load_config, load_identifiers
from .core import PublishError, report_hits, run
from .llm import LLMError
from .ocr import OCRError
from .names import Allowlist
from .verify import verify_texts, write_report


FOLDERS = pathlib.Path(__file__).resolve().parent / "folders"   # README for each data folder (the folders are git-ignored)


def init(paths):
    """Create the data folders with their READMEs, private/identifiers.toml and config/local.toml. Never overwrites."""
    for name in ("Sources", "private", "filtered", "analysis"):
        d = ROOT / name
        d.mkdir(exist_ok=True)
        if not (d / "README.md").exists():
            shutil.copy(FOLDERS / f"{name}.md", d / "README.md")
    for src, dst, what in ((ROOT / "config" / "identifiers.example.toml", paths.identifiers,
                            "Fill it in yourself: it holds the patient's identifiers, and Claude must not read it."),
                           (ROOT / "config" / "local.example.toml", ROOT / "config" / "local.toml",
                            "List your Sources/ subfolders in it.")):
        rel = dst.relative_to(ROOT).as_posix()
        if dst.exists():
            print(f"{rel} already exists; left unchanged.")
        else:
            shutil.copy(src, dst)
            print(f"Created {rel}. {what}")
    made = 0
    for src in load_config().get("sources", []):   # reload: local.toml may have just been created
        d = ROOT / src["path"]
        if not d.exists():
            d.mkdir(parents=True)
            made += 1
    print(f"Data folders ready: Sources/ ({made} new source folder(s)), private/, filtered/, analysis/. "
          "Next: python -m pipeline doctor")
    return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create private/ with an identifiers.toml template")
    r = sub.add_parser("run", help="de-identify all sources and publish if the leak check passes")
    r.add_argument("--no-llm", action="store_true", help="rules + identifiers only (never publishes)")
    r.add_argument("--accept-warnings", action="store_true", help="publish despite WARN hits you have reviewed")
    r.add_argument("--limit", type=int, help="process only the first N documents (testing)")
    sub.add_parser("verify", help="re-run the leak check on the published output")
    sub.add_parser("audit", help="count-only report of redacted PERSON entities (spots drug names etc.)")
    sub.add_parser("ids", help="count-only inventory of detected identifier values; values go to a private file")
    d = sub.add_parser("doctor", help="check this machine: Python, GPU, Ollama and model choice, optional tools")
    d.add_argument("--bench", action="store_true", help="score the model on a built-in synthetic note (recall, speed)")
    d.add_argument("--model", help="model to benchmark (default: the configured or recommended one)")
    args = ap.parse_args()

    cfg = load_config()
    paths = default_paths(cfg)
    if args.cmd == "doctor":
        from .doctor import doctor
        return doctor(cfg, paths, args)
    if args.cmd == "init":
        return init(paths)
    if args.cmd == "run":
        try:
            ok = run(cfg, paths, use_llm=not args.no_llm, accept_warnings=args.accept_warnings, limit=args.limit,
                     log=lambda *a, **k: print(*a, **k))
        except (LLMError, OCRError, PublishError) as e:
            print(f"ERROR: {e}")
            return 2
        return 0 if ok else 1
    if args.cmd == "ids":
        from .idreport import inventory
        inventory(cfg, paths)
        return 0
    if args.cmd == "audit":
        from .audit import audit
        audit(paths, cfg)
        return 0
    if args.cmd == "verify":
        notes = sorted((paths.output / "notes").glob("*.md"))
        texts = {p.stem.rsplit("_", 1)[-1]: p.read_text(encoding="utf-8") for p in notes}
        import json
        manifest = json.loads((paths.output / "manifest.json").read_text(encoding="utf-8"))
        ocr_ids = {e["doc_id"] for e in manifest if e.get("ocr_pages")}
        fails, warns = verify_texts(texts, load_identifiers(paths), paths.registry, Allowlist(cfg),
                                    cfg.get("policy", {}), ocr_ids)
        write_report(paths.private / "verify_report.md", fails, warns)
        print(f"Checked {len(texts)} published notes.")
        report_hits(fails, warns, print)
        return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
