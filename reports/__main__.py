"""python -m reports build [--case DIR] [--out DIR] [--only NAME ...]

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
    a = ap.parse_args(argv)
    if a.case:
        os.environ["PCR_CASE"] = a.case
    if a.out:
        os.environ["PCR_OUT"] = a.out
    if a.notes:
        os.environ["PCR_NOTES"] = a.notes
    from . import common
    c = common.case()
    wanted = a.only or [k for k in REPORTS if k in c.get("reports", REPORTS)]
    for name in wanted:
        importlib.import_module(f"reports.{REPORTS[name]}").main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
