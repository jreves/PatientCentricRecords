"""python -m reports build [--case DIR] [--out DIR] [--only NAME ...] [--no-audit]
       python -m reports audit [--suggest] [--no-semantic]

Builds every report from the case file. Reports: timelines (interactive pages, full timeline, chart pack, chart PDFs),
treatments, pathology, blood_counts, emergency, overview, medications, vitals, questions."""
import argparse
import importlib
import os
import sys

REPORTS = {
    "timelines": "timeline", "treatments": "treatments_table", "pathology": "pathology", "blood_counts": "blood_counts",
    "emergency": "emergency", "overview": "overview", "medications": "medications", "vitals": "vitals", "questions": "questions",
}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m reports", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the reports")
    b.add_argument("--case", help="case directory (default: analysis/case, or $PCR_CASE)")
    b.add_argument("--out", help="output directory (default: analysis/, or $PCR_OUT)")
    b.add_argument("--notes", help="published notes directory (default: the case's notes_dir, else the pipeline's filtered/notes)")
    b.add_argument("--only", nargs="*", choices=sorted(REPORTS), help="build only these reports")
    b.add_argument("--no-audit", action="store_true", help="skip the source audit after building")
    b.add_argument("--no-semantic", action="store_true", help="audit without the local-model reading")
    au = sub.add_parser("audit", help="check that every statement in the case cites a published note that supports it")
    au.add_argument("--case", help="case directory (default: analysis/case, or $PCR_CASE)")
    au.add_argument("--out", help="output directory (default: analysis/, or $PCR_OUT)")
    au.add_argument("--notes", help="published notes directory")
    au.add_argument("--no-semantic", action="store_true", help="skip the local-model reading of each claim")
    au.add_argument("--suggest", action="store_true", help="propose sources for unsourced claims (citations.suggested.yaml)")
    a = ap.parse_args(argv)
    if getattr(a, "case", None):
        os.environ["PCR_CASE"] = a.case
    if getattr(a, "out", None):
        os.environ["PCR_OUT"] = a.out
    if getattr(a, "notes", None):
        os.environ["PCR_NOTES"] = a.notes
    from . import common
    c = common.case()
    if a.cmd == "audit":
        from . import audit
        if a.suggest:
            audit.suggest()
            return 0
        audit.main(semantic=not a.no_semantic)
        return 0
    wanted = a.only or [k for k in REPORTS if k in c.get("reports", REPORTS)]
    for name in wanted:
        importlib.import_module(f"reports.{REPORTS[name]}").main()
    if not a.no_audit:   # warn-only: reports are built whatever the audit finds
        importlib.import_module("reports.audit").main(semantic=not a.no_semantic)
    return 0


if __name__ == "__main__":
    sys.exit(main())
