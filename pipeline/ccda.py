"""Read HL7 C-CDA XML documents (hospital "Summarization of Episode Note", discharge summaries...).

De-identification starts here, by construction: from the document header only an allowlist
is emitted (document kind, title, dates, the custodian organization's name, the encounter
location's name). The patient block (recordTarget), participants, informants, authors,
addresses, phone numbers and IDs are never extracted, so they cannot leak.

Each section's human-readable narrative (<text>) becomes one "page", with tables rendered as
"a | b | c" rows. The coded entries mirror the narrative and are not rendered. Sections listed
in DROP_SECTIONS are skipped. Everything emitted still goes through the normal rules, local
LLM and leak check.
"""
import re
import xml.etree.ElementTree as ET

NS = "{urn:hl7-org:v3}"
# LOINC section codes skipped entirely: insurance (member/policy IDs) and care team (may list
# family caregivers; the clinicians are already in the notes).
DROP_SECTIONS = {"48768-6": "insurance providers", "85847-2": "care team"}
EMPTY = re.compile(r"^\s*(?:no (?:data|information|known)[^\n]*|none(?: recorded| documented)?\.?|n/?a)\s*$", re.I)
BLOCK = {"paragraph", "br", "item", "caption", "footnote", "tr", "list", "table", "thead", "tbody", "content_block"}


def _t(el):
    return el.tag.split("}")[-1] if isinstance(el.tag, str) else ""


def _date(value):
    """HL7 TS '20241118120021-0600' -> '11/18/2024'."""
    m = re.match(r"(\d{4})(\d{2})(\d{2})", value or "")
    return f"{int(m.group(2))}/{int(m.group(3))}/{m.group(1)}" if m else None


def _render(el, out):
    """Narrative block -> lines. Tables become 'a | b | c' rows."""
    tag = _t(el)
    if tag == "table":
        for tr in el.iter(NS + "tr"):
            cells = [" ".join("".join(c.itertext()).split()) for c in tr if _t(c) in ("th", "td")]
            if any(cells):
                out.append("\n" + " | ".join(cells) + "\n")   # one row per line
        return
    if tag == "br":
        out.append("\n")
    if el.text and tag not in ("table",):
        out.append(el.text)
    for child in el:
        _render(child, out)
        if _t(child) in BLOCK:
            out.append("\n")
        if child.tail:
            out.append(child.tail)


def _narrative(text_el):
    out = []
    _render(text_el, out)
    lines = []
    for part in "".join(out).split("\n"):
        line = " ".join(part.split())
        if line:
            lines.append(line)
    return "\n".join(lines)


def is_ccda(root):
    return root.tag == NS + "ClinicalDocument"


def read(path):
    """-> list of page texts, or None if this XML is not a C-CDA document."""
    root = ET.parse(path).getroot()
    if not is_ccda(root):
        return None
    code = root.find(NS + "code")
    kind = (code.get("displayName") if code is not None else None) or "Clinical Document"
    title_el = root.find(NS + "title")
    title = " ".join((title_el.text or "").split()) if title_el is not None else kind

    span = root.find(f"{NS}documentationOf/{NS}serviceEvent/{NS}effectiveTime")
    if span is None:
        span = root.find(f"{NS}componentOf/{NS}encompassingEncounter/{NS}effectiveTime")
    low = high = None
    if span is not None:
        lo, hi = span.find(NS + "low"), span.find(NS + "high")
        low = _date(lo.get("value") if lo is not None else span.get("value"))
        high = _date(hi.get("value")) if hi is not None else None
    if low is None:
        eff = root.find(NS + "effectiveTime")
        low = _date(eff.get("value") if eff is not None else None)
    custodian = root.find(f"{NS}custodian/{NS}assignedCustodian/{NS}representedCustodianOrganization/{NS}name")
    facility = root.find(f"{NS}componentOf/{NS}encompassingEncounter/{NS}location/{NS}healthCareFacility/{NS}location/{NS}name")

    header = [title, f"C-CDA: {kind} | {low or '?'} to {high or low or '?'}"]
    if custodian is not None and (custodian.text or "").strip():
        header.append("Source: " + " ".join(custodian.text.split()))
    if facility is not None and (facility.text or "").strip():
        header.append("Location: " + " ".join(facility.text.split()))
    pages = ["\n".join(header)]

    body = root.find(f"{NS}component/{NS}structuredBody")
    if body is None:
        return pages   # nonXMLBody (embedded file): nothing readable; header only
    for sec in body.iter(NS + "section"):
        sc = sec.find(NS + "code")
        if sc is not None and sc.get("code") in DROP_SECTIONS:
            continue
        text_el = sec.find(NS + "text")
        text = _narrative(text_el) if text_el is not None else ""
        # Only truly empty sections are skipped: a short one can matter ("Reason for Visit: Hip dislocation").
        if not any(c.isalnum() for c in text) or EMPTY.match(text):
            continue
        st = sec.find(NS + "title")
        stitle = " ".join((st.text or "").split()) if st is not None else "Section"
        pages.append(f"{stitle}\n{text}")
    return pages
