"""Deterministic PII detectors: regex patterns and the user's known identifiers."""
import re
from dataclasses import dataclass
from datetime import date


@dataclass
class Span:
    start: int
    end: int
    cat: str               # PATIENT CLINICIAN PERSON FACILITY ADDRESS LOCATION PHONE EMAIL URL ID DOB OTHER
    source: str            # which detector produced it
    token: str | None = None


NAME_CATS = {"PATIENT", "CLINICIAN", "PERSON"}


def kept_categories(policy):
    """Registry categories published as written rather than pseudonymized."""
    kept = set()
    if not policy.get("redact_clinicians", True):
        kept.add("CLINICIAN")
    if not policy.get("redact_facilities", True):
        kept.add("FACILITY")
    return kept

MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
         r"|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
DATE = (r"(?<![\d/])(?:\d{1,2}[/-]\d{1,2}[/-](?:\d{4}|\d{2})"
        r"|\d{4}-\d{1,2}-\d{1,2}"
        rf"|{MONTH}\.?[ \t]+\d{{1,2}}(?:st|nd|rd|th)?,?[ \t]+\d{{4}}"
        rf"|\d{{1,2}}[- ]{MONTH}[- ,]+\d{{2,4}})(?![\d/])")
DATE_RE = re.compile(DATE, re.I)

# --- names ------------------------------------------------------------------
NAME_WORD = r"[A-Z][a-zA-Z'\-]+"
_STOP = (r"(?!(?:DOB|MRN|DOS|Date|Age|Sex|Gender|Acct|Account|Phone|Fax|Provider|Visit|Encounter|Room"
         r"|Location|Female|Male|Patient|Race|PCP|Ref|Referring|Attending|Signed|Page|Printed|Time"
         r"|Dept|Department|Specialty|Facility|Service|Status|Type|Reason|Chief|History|Diagnosis)\b)")
PERSON_NAME = (rf"{_STOP}{NAME_WORD}(?:(?:,[ \t]*|[ \t]+){_STOP}"
               rf"(?:[A-Z]\.?(?![a-zA-Z])|{NAME_WORD})){{0,3}}")
TITLE_OPT = r"(?:(?:Dr|Mr|Mrs|Ms|Miss|Mx)\.?[ \t]+)?"
CRED_ALT = (r"(?:M\.?D\.?|D\.O\.|DO|N\.?P\.?|PA-C|R\.?N\.?|APRN|FNP(?:-[A-Z]{1,2})?|ANP(?:-BC)?|AOCNP"
            r"|DNP|CNP|CRNP|Ph\.?D\.?|PharmD|RPh|MSN|LCSW|MBBS|FACS|FACP)")
_NOT_AFTER_WORD = r"(?<![A-Za-z][ \t])"  # label must not continue another word ("Drug Name:")

CLINICIAN_LABELS = (r"(?:Provider|Attending(?:[ \t]+Physician)?|Referring(?:[ \t]+(?:Physician|Provider|MD))?"
                    r"|Ordering(?:[ \t]+(?:Physician|Provider|MD))?|PCP|Primary[ \t]+Care(?:[ \t]+(?:Physician|Provider))?"
                    r"|Physician|Surgeon|Oncologist|Pathologist|Radiologist|Author|Resident|Fellow|cc)")
PATIENT_LABELS = r"(?:Patient(?:[ \t]+Name)?|Pt(?:[ \t]+Name)?|Name)"
PERSON_LABELS = (r"(?:Guarantor|Emergency[ \t]+Contact|Next[ \t]+of[ \t]+Kin|Spouse|Husband|Wife|Contact"
                 r"|Guardian|Caregiver|Daughter|Son|Mother|Father|Sister|Brother)")
BY_VERBS = (r"(?:(?:Electronically[ \t]+)?Signed|Co-?signed|Dictated|Transcribed|Authenticated|Interpreted"
            r"|Reviewed|Performed|Seen|Referred|Verified|Approved)")

NAME_RULES = [
    ("title-name", re.compile(rf"\b(?P<t>Dr|Mr|Mrs|Ms|Miss|Mx)\.?[ \t]+(?P<n>{_STOP}{NAME_WORD}"
                              rf"(?:[ \t]+(?:[A-Z]\.[ \t]+)?{_STOP}{NAME_WORD})?)"), None),
    ("credential-name", re.compile(
        rf"\b(?P<n>{NAME_WORD}(?:[ \t]+[A-Z]\.?)?(?:[ \t]+{NAME_WORD}){{1,2}}"
        rf"|{NAME_WORD},[ \t]*{NAME_WORD}(?:[ \t]+[A-Z]\.?)?),?[ \t]+{CRED_ALT}(?![A-Za-z])(?![ \t]+Anderson)"),
     "CLINICIAN"),
    ("by-name", re.compile(rf"\b(?i:{BY_VERBS}[ \t]+by):?[ \t]+{TITLE_OPT}(?P<n>{PERSON_NAME})"), "CLINICIAN"),
    ("clinician-label", re.compile(rf"{_NOT_AFTER_WORD}\b{CLINICIAN_LABELS}[ \t]*[:#][ \t]*{TITLE_OPT}(?P<n>{PERSON_NAME})"),
     "CLINICIAN"),
    ("patient-label", re.compile(rf"{_NOT_AFTER_WORD}\b{PATIENT_LABELS}[ \t]*:[ \t]*{TITLE_OPT}(?P<n>{PERSON_NAME})"),
     "PATIENT"),
    ("person-label", re.compile(rf"{_NOT_AFTER_WORD}\b{PERSON_LABELS}[ \t]*:[ \t]*{TITLE_OPT}(?P<n>{PERSON_NAME})"),
     "PERSON"),
]

# --- other identifiers --------------------------------------------------------
ID_LABEL = (r"(?:ID[ \t]*#|MRN|MR[ \t]*#|MR[ \t]*No\.?|Med(?:ical)?[ \t]+Rec(?:ord)?(?:[ \t]+(?:Number|No\.?|#))?"
            r"|Acct|Account|Patient[ \t]+ID|Pt[ \t]+ID|PID|FIN|CSN|HAR|Enc(?:ounter)?[ \t]*(?:#|No\.?|Number|ID|CSN)"
            r"|NPI|Member[ \t]*(?:ID|#|No\.?)|Subscriber[ \t]*(?:ID|#|No\.?)|Policy[ \t]*(?:#|No\.?|Number|ID)?"
            r"|Group[ \t]*(?:#|No\.?|Number)|Order[ \t]*(?:#|No\.?|Number|ID)|Accession[ \t]*(?:#|No\.?|Number)?"
            r"|Acc[ \t]*#|Specimen[ \t]*(?:#|No\.?|ID|Number)|Case[ \t]*(?:#|No\.?|Number)"
            r"|Req(?:uisition)?[ \t]*(?:#|No\.?)|Claim[ \t]*(?:#|No\.?|Number)|SSN"
            r"|Social[ \t]+Security(?:[ \t]+(?:Number|No\.?|#))?)")
STREET_SUFFIX = (r"(?:St|Street|Rd|Road|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Ct|Court|Pkwy|Parkway"
                 r"|Hwy|Highway|Cir|Circle|Pl|Place|Trl|Trail|Loop|Pike|Ter|Terrace|Sq|Square|Cv|Cove|Xing|Crossing)")

# State codes for "City, ST". Omitted on purpose: MD, PA, MS, ID (credentials and labels:
# "Kulkarni, MD", "Lee, PA-C"). Mixed-case forms ("Tx") skip ones that are words or lab
# symbols (In, Or, Ok, Ca, Mg...). A code followed by digits is a lab ("CA 27-29"), not a place.
STATE_CODES = ("AL|AK|AZ|AR|CA|CO|CT|DC|DE|FL|GA|HI|IA|IL|IN|KS|KY|LA|MA|ME|MI|MN|MO|MT|NC|ND|NE|NH|NJ|NM|NV|NY"
               "|OH|OK|OR|RI|SC|SD|TN|TX|UT|VA|VT|WA|WI|WV|WY")
STATE_MIXED = "Tx|Fl|Ga|Az|Nm|Ny|Nj|Nc|Sc|Wa|Va|Tn|Ky|Ut|Nv|Ks|Ct|Vt|Wv|Wy|Nd|Sd|Ri|Mt|Nh"
STATE_NAMES = ("Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho"
               "|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota"
               "|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York"
               "|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina"
               "|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming")

PATTERN_RULES = [
    # No leading \b: in space-less PDFs the label is glued to the name before it ("...DoeDOB:").
    ("dob", re.compile(rf"(?:DOB|D\.O\.B\.?|Date[ \t]*of[ \t]*Birth|Birth[ \t]*date|\bBorn)[ \t]*[:#]?[ \t]*(?P<v>{DATE})",
                       re.I), "DOB"),
    ("labeled-id", re.compile(rf"\b{ID_LABEL}[ \t]*(?:[:#.][ \t]*){{0,2}}(?P<v>(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9\-]{{3,}})",
                              re.I), "ID"),
    ("ssn", re.compile(r"(?<!\d)(?P<v>\d{3}-\d{2}-\d{4})(?!\d)"), "ID"),
    ("phone", re.compile(r"(?<![\d-])(?P<v>(?:\+?1[-. \t]?)?(?:\(\d{3}\)[ \t]?|\d{3}[-. ])\d{3}[-. ]\d{4})(?![\d-])"),
     "PHONE"),
    ("email", re.compile(r"(?P<v>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)"), "EMAIL"),
    ("url", re.compile(r"(?P<v>\b(?:https?://|www\.)\S+)", re.I), "URL"),
    # Label on its own line, value on the next (portal demographics PDFs, 2026-09-28: "Patient Identifier\n583014"
    # got through). Identifier labels -> [ID]; specific name labels -> [REDACTED]. Bare "Name" is excluded: PDF
    # medication tables use it as a column header.
    ("id-next-line", re.compile(r"^(?:Patient[ \t]*Identifier|Identifier|MRN|Medical[ \t]*Record[ \t]*(?:Number|No\.?|#)"
                                r"|Member[ \t]*(?:ID|Number|#)|Subscriber[ \t]*(?:ID|Number|#)|Policy[ \t]*(?:Number|No\.?|#)"
                                r"|Group[ \t]*(?:Number|No\.?|#)|Account[ \t]*(?:Number|No\.?|#)|Social[ \t]*Security[ \t]*Number|SSN)"
                                r"[ \t]*:?[ \t]*\n[ \t]*(?P<v>[A-Za-z0-9][A-Za-z0-9 \-]{2,30})[ \t]*$", re.M | re.I), "ID"),
    ("name-next-line", re.compile(r"^(?:(?:Previous|Legal|Preferred|Maiden|Former|Other|Patient|Full|Birth)[ \t]*Names?|Alias(?:es)?"
                                  r"|Emergency[ \t]*Contacts?|Guarantor|Next[ \t]*of[ \t]*Kin|Contact[ \t]*Name|Caregiver|Guardian)"
                                  r"[ \t]*\*?:?[ \t]*\n[ \t]*(?P<v>(?=[^\n]*[A-Za-z0-9])(?![^\n]*:[ \t]*$)[^\n\[]{2,80}?)[ \t]*$", re.M | re.I), "OTHER"),
    # "Full Encounter Summary" exports print the patient ID on its own line, away from "ID#".
    ("id-own-line", re.compile(r"^(?P<v>\d{5,8})[ \t]+Date/Time$", re.M), "ID"),
    ("long-number", re.compile(r"(?<![\w.])(?P<v>[A-Z]{0,3}-?\d{7,}[A-Z]?)(?![\d.])"), "ID"),
    ("street", re.compile(rf"(?P<v>\b\d{{1,6}}[ \t]+(?:[NSEW]\.?[ \t]+)?(?:[A-Z][a-zA-Z0-9'\-]*[ \t]+){{1,4}}"
                          rf"{STREET_SUFFIX}\b\.?(?:,?[ \t]+(?:Suite|Ste|Apt|Unit|Bldg|Building|#)\.?[ \t]*[A-Z0-9-]+)?)"),
     "ADDRESS"),
    ("po-box", re.compile(r"(?P<v>\bP\.?[ \t]?O\.?[ \t]+Box[ \t]+\d+)", re.I), "ADDRESS"),
    # ZIP may be 5 digits, ZIP+4, or 9 digits run together (seen in hospital records).
    # Some PDFs drop the spaces ("Millbrook,TX78990"): a comma is then required before the state.
    ("city-state-zip", re.compile(rf"(?P<v>\b(?:\d{{1,6}}[ \t]+)?(?:[A-Z][a-zA-Z.'\-]+[ \t]){{0,5}}[A-Z][a-zA-Z.'\-]+"
                                  rf"(?:,[ \t]*|[ \t]+)(?:[A-Z]{{2}}|{STATE_NAMES})[ \t]*\d{{5}}(?:-?\d{{4}})?)(?!\d)"), "ADDRESS"),
    # The same when the city itself was already redacted: "[PERSON-93],TX78990" -> the state + ZIP still go.
    ("state-zip-after-token", re.compile(rf"\],[ \t]*(?P<v>(?:[A-Z]{{2}}|{STATE_NAMES})[ \t]*\d{{5}}(?:-?\d{{4}})?)(?!\d)"), "ADDRESS"),
    # "originally from Springville, Tx", "[Lakeview, CO]", and address lines whose street has
    # no standard suffix ("123 Sunset Bend Millbrook, TX"): an optional house number and up to 5 words.
    # A state code followed by 1-3 digits is a lab value ("CA 27-29", "CA 125"), not a place.
    ("city-state", re.compile(rf"(?P<v>\b(?:\d{{1,6}}[ \t]+)?(?:[A-Z][a-zA-Z'\-]+[ \t]){{0,5}}[A-Z][a-zA-Z'\-]+,[ \t]*"
                              rf"(?:{STATE_CODES}|{STATE_MIXED}|{STATE_NAMES}))(?![\w-])(?![ \t]*-?\d{{1,3}}(?!\d))"),
     "LOCATION"),
]


def detect(text, denylist):
    spans = []
    for name, rx, hint in NAME_RULES:
        for m in rx.finditer(text):
            cat = hint or ("CLINICIAN" if m.group("t") == "Dr" else "PERSON")
            spans.append(Span(m.start("n"), m.end("n"), cat, name))
    for name, rx, cat in PATTERN_RULES:
        for m in rx.finditer(text):
            spans.append(Span(m.start("v"), m.end("v"), cat, name))
    spans += denylist.find(text)
    return spans


# --- known identifiers (private/identifiers.toml) ----------------------------
def date_variants(iso):
    d = date.fromisoformat(iso)
    m, dd, y, yy = d.month, d.day, d.year, d.year % 100
    full, ab = d.strftime("%B"), d.strftime("%b")
    return {f"{m}/{dd}/{y}", f"{m:02}/{dd:02}/{y}", f"{m}/{dd}/{yy:02}", f"{m:02}/{dd:02}/{yy:02}",
            f"{m}-{dd}-{y}", f"{m:02}-{dd:02}-{y}", d.isoformat(), f"{y}{m:02}{dd:02}",
            f"{full} {dd}, {y}", f"{full} {dd} {y}", f"{ab} {dd}, {y}", f"{ab}. {dd}, {y}", f"{ab} {dd} {y}",
            f"{dd} {full} {y}", f"{dd} {ab} {y}", f"{dd}-{ab}-{y}", f"{dd:02}-{ab}-{y}", f"{dd}-{ab}-{yy:02}"}


def _edge(c, side):
    """A boundary only against the same kind of character. Some PDFs lose their spaces, gluing a value to the next
    word ("...:<DOB>ExamDate"), and a digit edge must still match there (2026-09-28: a DOB leaked this way)."""
    if c.isdigit():
        return r"(?<![0-9])" if side == "pre" else r"(?![0-9])"
    if c.isalpha():
        return r"(?<![A-Za-z])" if side == "pre" else r"(?![A-Za-z])"
    return ""


def literal_pattern(s):
    """Whitespace-flexible, boundary-anchored (per character kind), case-insensitive literal."""
    s = s.strip()
    body = r"\s*".join(re.escape(w) for w in s.split())
    return re.compile(_edge(s[:1], "pre") + body + _edge(s[-1:], "post"), re.I)


ID_LABEL_PREFIX = re.compile(r"^[A-Za-z][A-Za-z #./]{0,24}:[ \t]*")


def normalized_ids(identifiers):
    """[patient] ids as the user listed them -> (ids, date-like entries). Entries copied with their label
    ("MRN: 1234567", "DOB: 4/12/19xx") keep only the value, so the label text stays readable, and dates are
    returned separately to be handled as a DOB (2026-09-28: a copied "DOB: <date>" turned [DOB] into [ID])."""
    ids, dates = [], []
    for v in identifiers.get("patient", {}).get("ids", []):
        v = ID_LABEL_PREFIX.sub("", v.strip()).strip()
        if not v:
            continue
        (dates if DATE_RE.fullmatch(v) else ids).append(v)
    return ids, dates


class Denylist:
    """Non-name identifiers the user listed. Names go through the Registry instead."""

    def __init__(self, identifiers):
        p = identifiers.get("patient", {})
        self.patterns = []   # (regex, cat)
        if p.get("dob"):
            self.patterns += [(literal_pattern(v), "DOB") for v in date_variants(p["dob"])]
        ids, dob_like = normalized_ids(identifiers)
        for v in ids:
            self.patterns.append((literal_pattern(v), "ID"))
        for v in dob_like:   # a date listed under ids is a date of birth, not an ID ([DOB; age N] survives)
            self.patterns.append((literal_pattern(v), "DOB"))
        for v in p.get("phones", []):
            digits = re.sub(r"\D", "", v)[-10:]
            if len(digits) == 10:
                sep = r"[-. \t()]*"
                self.patterns.append((re.compile(r"(?<!\d)\(?" + digits[:3] + r"\)?" + sep + digits[3:6] + sep
                                                 + digits[6:] + r"(?!\d)"), "PHONE"))
        for v in p.get("emails", []):
            self.patterns.append((literal_pattern(v), "EMAIL"))
        for v in p.get("addresses", []):
            parts = [v] + [part.strip() for part in v.split(",")]
            for part in parts:
                if len(part) >= 4 and not re.fullmatch(r"[A-Z]{2}", part):
                    self.patterns.append((literal_pattern(part), "ADDRESS"))
        for v in identifiers.get("redact", {}).get("terms", []):
            self.patterns.append((literal_pattern(v), "OTHER"))

    def find(self, text):
        return [Span(m.start(), m.end(), cat, "denylist")
                for rx, cat in self.patterns for m in rx.finditer(text)]
