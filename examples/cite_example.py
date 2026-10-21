"""Rebuild the example case's citations (examples/case/citations.yaml) from its fictional notes.

    python examples/cite_example.py

Keeps the hand-made demonstration entries, adds machine-found citations for the rest, then a few by hand. Run it after
changing the example's notes or case; then `python -m reports audit --case examples/case --out examples/out`.
"""
import os
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PCR_OUT", str(ROOT / "examples" / "out"))
from reports import case as case_mod  # noqa: E402

case_mod.load(ROOT / "examples" / "case")
from reports import audit  # noqa: E402

HEAD = ("# EXAMPLE (fictional): citations for the example's statements. Most were found by `reports audit --suggest`\n"
        "# from the fictional notes; a few are by hand, and a few show the other statuses (family report, partly grounded,\n"
        "# no source yet). Rebuilt by examples/cite_example.py.\n")
DEMO = {   # entries that demonstrate each status
    "emergency/lab/CA 27-29": {"src": [{"doc": "ex00000001", "quote": "CA 27-29 47 U/mL on 9/15/2026, stable."}]},
    "emergency/team/Oncologist": {"src": [{"doc": "ex00000001", "quote": "Provider: Owen Tremblay, MD"}]},
    "emergency/risk/Diarrhea": {"src": [{"doc": "ex00000001", "quote": "diarrhea controlled with loperamide"}]},
    "emergency/med/Ondansetron": {"src": [{"doc": "ex00000001", "quote": "Tolerating treatment"}],
                                  "reviewed": "deliberately cited to a note that doesn't mention ondansetron, to show 'partly grounded'"},
    "emergency/vaccine/Influenza": {"src": [{"family": "the family, 9/2026"}]},
}
HAND = {
    "questions/gaps/Germline testing": {"src": [{"absent": "germline|BRCA"}]},
    "emergency/fill/Blood type": {"src": [{"doc": "ex00000002", "quote": "Blood Type ABO/Rh: O POS"}]},
    "emergency/fill/Allergies": {"src": [{"doc": "ex00000009", "quote": "Sulfa (rash)"}]},
    "emergency/hospitals": {"src": [{"doc": "ex00000002", "quote": "Admitted 2/11/2025 with dehydration and diarrhea on capecitabine."}]},
    "therapy/radiation/T10 spine/2021-03-01": {"src": [{"doc": "ex00000009", "quote": "radiation T10 spine [20 Gy / 5 fx]: 3/1/2021 - 3/5/2021, palliative"}]},
    "imaging/2021-09-14": {"src": [{"doc": "ex00000009", "quote": "bone scan [9/14/2021] = lesions less active"}]},
    "imaging/2025-08-26": {"src": [{"doc": "ex00000009", "quote": "PROGRESSION: CT [8/26/2025] = liver progression"}]},
    "treatments/phase/Early breast cancer": {"src": [{"doc": "ex00000009", "quote": "screening mammogram [4/14/2015] = left breast mass"}]},
    "treatments/phase/Metastatic": {"src": [{"doc": "ex00000009", "quote": "METASTATIC RECURRENCE: PET [2/18/2021]"}]},
    "pathology/untested/2024-05-14": {"src": [{"doc": "ex00000009", "quote": "PROGRESSION: CT [5/14/2024] = liver lesions larger, new lung nodule"}]},
    "pathology/untested/2025-08-26": {"src": [{"doc": "ex00000009", "quote": "PROGRESSION: CT [8/26/2025] = liver progression"}]},
    "overview/negative": {"src": [{"absent": r"brain|head CT|MRI head"}]},
    "questions/settled/PIK3CA test": {"src": [{"doc": "ex00000009", "quote": "liquid bx [5/30/2023] = PIK3CA H1047R, ESR1 not detected"}]},
    "emergency/risk/Neutropenia risk": {"src": [{"doc": "ex00000009", "quote": "neutropenia grade 3 [11/20/2025]; growth factor added"}]},
    "emergency/risk/Bone metastases": {"src": [{"doc": "ex00000009", "quote": "new T10 and right iliac bone lesions"}]},
    "emergency/risk/On denosumab": {"src": [{"doc": "ex00000009", "quote": "denosumab 120 mg monthly from 3/15/2021"}]},
}

cit = dict(DEMO) | HAND
audit.SOURCES.write_text(HEAD + yaml.safe_dump(cit, allow_unicode=True, sort_keys=False, width=140), encoding="utf-8")
audit.suggest(log=lambda *a: None)
for k, v in (yaml.safe_load(audit.SUGGESTED.read_text(encoding="utf-8")) or {}).items():
    cit.setdefault(k, {"src": v["src"]})
audit.SUGGESTED.unlink()
audit.SOURCES.write_text(HEAD + yaml.safe_dump(cit, allow_unicode=True, sort_keys=False, width=140), encoding="utf-8")
out = audit.run(semantic=False, log=print)
