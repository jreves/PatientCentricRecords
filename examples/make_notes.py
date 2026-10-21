"""Generate the example case's fictional de-identified notes (examples/case/notes). Every value is invented.

    python examples/make_notes.py

The notes use the layout the report readers expect: a "LabResults <dates>" table, vital-sign lines and a
"Medications:" block, in the same shape as an oncology EHR visit note after de-identification.
"""
import pathlib

NOTES = pathlib.Path(__file__).resolve().parent / "case" / "notes"

HEADER = """---
doc_id: {id}
date: {date}
date_basis: "label 'Date of Service'"
type: {type}
clinic: Example Cancer Center
patient_age: {age}
source: example (fictional)
format: pdf
pages: 1
redactions: 3
pipeline_version: 0.8.3
---

## Page 1

FICTIONAL EXAMPLE NOTE. Every name and value is invented.
Patient: [PATIENT]   DOB: [DOB; age {age}]   MRN: [ID]
Date of Service: {mdy}
Provider: {provider}
"""

# The running oncology history every visit note carries (the lines dated up to that visit), as real EHR notes do.
HISTORY = [
    ("2015-04-14", "--screening mammogram [4/14/2015] = left breast mass"),
    ("2015-05-06", "===> L lumpectomy + sentinel LN bx [5/6/2015] = 2.1 cm invasive ductal carcinoma, 1/3 LN+, ER 95%, PR 60%, HER2 1+ (Dr. Maya Lindqvist)"),
    ("2015-06-01", "===> adjuvant AC --> paclitaxel: doxorubicin + cyclophosphamide every 2 weeks x4 6/2015 - 8/2015, then paclitaxel weekly x12 8/2015 - 11/2015"),
    ("2015-12-07", "===> whole breast radiation [50 Gy / 25 fx]: 12/7/2015 - 1/8/2016 (Dr. Priya Raman)"),
    ("2016-01-10", "===> tamoxifen 1/2016 - 2/2018 --> switched to letrozole for hot flashes"),
    ("2018-02-01", "===> letrozole 2.5 mg daily 2/2018 - 2/2021 (adjuvant)"),
    ("2021-02-18", "METASTATIC RECURRENCE: PET [2/18/2021] = new T10 and right iliac bone lesions"),
    ("2021-02-24", "--CT-guided bx T10 [2/24/2021] = metastatic breast carcinoma, ER 90%, PR 0%, HER2 0"),
    ("2021-03-01", "===> radiation T10 spine [20 Gy / 5 fx]: 3/1/2021 - 3/5/2021, palliative (Dr. Priya Raman)"),
    ("2021-03-15", "===> letrozole + palbociclib 125 mg (3 weeks on / 1 off): 3/15/2021 - 6/1/2023; denosumab 120 mg monthly from 3/15/2021"),
    ("2021-09-14", "--bone scan [9/14/2021] = lesions less active"),
    ("2022-08-30", "--CT [8/30/2022] = stable bone disease, no visceral disease"),
    ("2023-05-22", "PROGRESSION: CT [5/22/2023] = new liver lesions (2), largest 1.4 cm"),
    ("2023-05-30", "--liquid bx [5/30/2023] = PIK3CA H1047R, ESR1 not detected"),
    ("2023-06-20", "===> fulvestrant 500 mg monthly + alpelisib 300 mg daily: 6/20/2023 - 5/20/2024"),
    ("2023-10-30", "--hyperglycemia grade 3 on alpelisib [10/30/2023]; ED 11/2/2023 for hyperglycemia, treated and released"),
    ("2023-12-05", "--CT [12/5/2023] = liver lesions smaller"),
    ("2024-01-15", "--dental extraction 1/15/2024; denosumab held 1/8/2024 - 3/4/2024"),
    ("2024-05-14", "PROGRESSION: CT [5/14/2024] = liver lesions larger, new lung nodule"),
    ("2024-06-03", "===> capecitabine 1000 mg/m2 twice daily, days 1-14 q21 days: 6/3/2024 - 9/10/2025 (Dr. Owen Tremblay)"),
    ("2024-11-05", "--hand-foot syndrome grade 2 [11/5/2024] --> capecitabine 750 mg/m2"),
    ("2025-02-11", "--admitted 2/11/2025 - 2/14/2025 for dehydration and diarrhea"),
    ("2025-08-26", "PROGRESSION: CT [8/26/2025] = liver progression"),
    ("2025-10-06", "===> sacituzumab govitecan 10 mg/kg days 1 and 8 q21 days: from 10/6/2025 (Dr. Owen Tremblay)"),
    ("2025-11-20", "--neutropenia grade 3 [11/20/2025]; growth factor added; 7.5 mg/kg from cycle 3"),
    ("2026-01-12", "--CT [1/12/2026] = partial response in the liver"),
    ("2026-08-25", "--CT [8/25/2026] = stable"),
]

# (id, date, provider, story, labs {date: (WBC, ANC, HGB, PLT)}, weight lb, Karnofsky, pain, medicines)
VISITS = [
    ("ex00000003", "2024-06-03", "Owen Tremblay, MD", "Starting capecitabine 1000 mg/m2 twice daily, days 1-14 every 21 days, after liver "
     "progression on fulvestrant + alpelisib.", {"2024-05-20": (6.1, 3.9, 12.8, 241), "2024-06-03": (5.8, 3.6, 12.6, 236)}, 152, 90, 1,
     ["Capecitabine Oral 1000 mg/m2 twice daily days 1-14", "Ondansetron Oral 8 mg every 8 hours as needed", "Omeprazole Oral 20 mg daily"]),
    ("ex00000004", "2024-11-04", "Owen Tremblay, MD", "Hand-foot syndrome grade 2; capecitabine reduced to 750 mg/m2. CT 10/2024: liver "
     "lesions smaller.", {"2024-10-21": (4.9, 2.8, 12.1, 212), "2024-11-04": (5.2, 3.1, 12.0, 219)}, 150, 80, 2,
     ["Capecitabine Oral 750 mg/m2 twice daily days 1-14", "Ondansetron Oral 8 mg every 8 hours as needed", "Omeprazole Oral 20 mg daily",
      "Urea cream 20% to hands and feet twice daily"]),
    ("ex00000005", "2025-03-10", "Owen Tremblay, MD", "Recovered from the 2/2025 admission for dehydration. Continuing capecitabine.",
     {"2025-02-24": (5.5, 3.4, 11.6, 205), "2025-03-10": (5.9, 3.7, 11.9, 221)}, 147, 80, 2,
     ["Capecitabine Oral 750 mg/m2 twice daily days 1-14", "Ondansetron Oral 8 mg every 8 hours as needed", "Omeprazole Oral 20 mg daily"]),
    ("ex00000006", "2025-09-08", "Owen Tremblay, MD", "CT 8/26/2025: liver progression. Stopping capecitabine; plan sacituzumab govitecan.",
     {"2025-08-25": (6.0, 3.8, 12.2, 230), "2025-09-08": (6.2, 4.0, 12.3, 228)}, 146, 80, 3,
     ["Ondansetron Oral 8 mg every 8 hours as needed", "Omeprazole Oral 20 mg daily", "Hydrocodone-Acetaminophen Oral 5-325 mg as needed"]),
    ("ex00000007", "2025-11-24", "Owen Tremblay, MD", "Sacituzumab govitecan cycle 3. Neutropenia grade 3 after cycle 2 (ANC 0.8 on "
     "11/17/2025); growth factor added, dose reduced to 7.5 mg/kg.", {"2025-11-17": (2.1, 0.8, 10.9, 176), "2025-11-24": (4.4, 2.6, 11.0, 188)},
     144, 70, 2, ["Ondansetron Oral 8 mg every 8 hours as needed", "Olanzapine 5 mg at bedtime", "Loperamide Oral 2 mg as needed",
                  "Omeprazole Oral 20 mg daily", "Hydrocodone-Acetaminophen Oral 5-325 mg as needed"]),
    ("ex00000008", "2026-01-12", "Owen Tremblay, MD", "CT 1/12/2026: partial response in the liver. Tolerating sacituzumab at 7.5 mg/kg.",
     {"2025-12-29": (4.8, 2.9, 11.2, 195), "2026-01-12": (5.1, 3.2, 11.4, 201)}, 145, 80, 1,
     ["Ondansetron Oral 8 mg every 8 hours as needed", "Olanzapine 5 mg at bedtime", "Loperamide Oral 2 mg as needed",
      "Omeprazole Oral 20 mg daily"]),
    ("ex00000009", "2026-05-11", "Owen Tremblay, MD", "Stable on sacituzumab. Mild fatigue.",
     {"2026-04-27": (4.6, 2.7, 11.3, 199), "2026-05-11": (4.9, 3.0, 11.5, 204)}, 145, 80, 1,
     ["Ondansetron Oral 8 mg every 8 hours as needed", "Loperamide Oral 2 mg as needed", "Omeprazole Oral 20 mg daily"]),
]


def table(labs):
    dates = sorted(labs, reverse=True)
    mdy = lambda d: f"{d[5:7]}/{d[8:10]}/{d[:4]}"
    rows = [("WBC x 10^3/uL", 0), ("Neu # (ANC) x 10^3/uL", 1), ("HGB g/dL", 2), ("PLT x 10^3/uL", 3)]
    return "\n".join([f"LabResults {' '.join(mdy(d) for d in dates)}"] + [f"{name} {' '.join(f'{labs[d][i]:g}' for d in dates)}" for name, i in rows])


def visit(id, date, provider, story, labs, weight, kps, pain, meds):
    age = 56 if date < "2025-08-01" else 57 if date < "2026-08-01" else 58
    text = HEADER.format(id=id, date=date, type="oncology-follow-up", age=age, mdy=f"{date[5:7]}/{date[8:10]}/{date[:4]}", provider=provider)
    history = "\n".join(line for d, line in HISTORY if d <= date)
    text += f"""
Diagnosis*:
Metastatic ER/PR+, HER-2 negative breast cancer:
{history}

History of Present Illness:
Follow-up for metastatic HR+/HER2- breast cancer (bone and liver). {story}

Medications:
{chr(10).join(meds)}
Medications reviewed and reconciled with patient.
Allergies:
Sulfa (rash)

Vitals:
Weight: {weight} lb, Pain Scale: {pain}
Karnofsky: {kps}%

Labs:
{table(labs)}

Plan: see the history above.
Electronically signed by: {provider}
"""
    return text


HOSPITAL = HEADER.format(id="ex00000002", date="2025-02-11", type="inpatient-summary", age=56, mdy="02/11/2025",
                         provider="Example General Hospital hospitalist") + """
Inpatient Summary
Admitted 2/11/2025 with dehydration and diarrhea on capecitabine. IV fluids; capecitabine held.
Discharged 2/14/2025, improved.
Blood Type ABO/Rh: O POS
"""

if __name__ == "__main__":
    NOTES.mkdir(parents=True, exist_ok=True)
    for v in VISITS:
        (NOTES / f"{v[1]}_oncology-follow-up_{v[0]}.md").write_text(visit(*v), encoding="utf-8")
    (NOTES / "2025-02-11_inpatient-summary_ex00000002.md").write_text(HOSPITAL, encoding="utf-8")
    print(f"wrote {len(VISITS) + 1} fictional notes to {NOTES}")
