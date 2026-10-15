"""`python -m pipeline doctor`: check this machine before a run.

Reports the platform, memory and GPU, whether Ollama is installed and running (and on the GPU), which installed model
suits the de-identification pass, and the optional tools (Tesseract for scans, Node + docx for the Word summary, a
Chromium browser for PDFs). It never installs or downloads anything: it prints the command to run instead.
`--bench` scores a model on a built-in synthetic note (invented identifiers) for recall and speed.

Output is status lines only: no file names from Sources/, nothing from private/.
"""
import importlib.util
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from .config import ROOT

GB = 1024 ** 3

# Models tested for this pipeline's identifier detection, best first. need_gb: approximate GPU memory for the model at
# num_ctx 8192 (weights + context). Models not listed here are untested: score them with `doctor --bench --model NAME`.
MODELS = [
    {"name": "qwen3:14b", "need_gb": 11, "download_gb": 9.3, "recommended": True,
     "note": "best recall in testing, including titled names and bare surnames"},
    {"name": "gemma4:12b", "need_gb": 10, "recommended": True, "note": "similar recall to qwen3:14b"},
    {"name": "qwen3.5:9b", "need_gb": 8, "recommended": False, "note": "faster, but missed titled names and bare surnames"},
    {"name": "granite4.2:8b", "need_gb": 7, "recommended": False, "note": "faster, but missed titled names and bare surnames"},
]

# --- output ------------------------------------------------------------------------------------------------------------

class Report:
    def __init__(self):
        self.fails = self.warns = 0

    def section(self, title):
        print(f"\n{title}")

    def line(self, status, text):
        self.fails += status == "FAIL"
        self.warns += status == "WARN"
        print(f"  [{status:4}] {text}")

    ok = lambda self, t: self.line("OK", t)
    warn = lambda self, t: self.line("WARN", t)
    fail = lambda self, t: self.line("FAIL", t)
    info = lambda self, t: self.line("INFO", t)
    todo = lambda self, t: print(f"         -> {t}")


def run_cmd(args, timeout=15):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


# --- hardware ----------------------------------------------------------------------------------------------------------

def total_ram():
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("pf", ctypes.c_ulonglong), ("apf", ctypes.c_ulonglong),
                            ("virt", ctypes.c_ulonglong), ("avirt", ctypes.c_ulonglong), ("ext", ctypes.c_ulonglong)]
            m = MS()
            m.len = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.total
        if sys.platform == "darwin":
            return int(run_cmd(["sysctl", "-n", "hw.memsize"]) or 0)
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (OSError, ValueError, AttributeError):
        return 0


def gpus():
    """[(vendor, name, memory bytes)] for the GPUs Ollama could use. Apple Silicon reports unified memory."""
    out = []
    smi = run_cmd(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    for row in (smi or "").splitlines():
        name, _, mib = row.rpartition(",")
        if mib.strip().isdigit():
            out.append(("NVIDIA", name.strip(), int(mib) * 1024 ** 2))
    if sys.platform == "darwin" and platform.machine() == "arm64":
        chip = run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"]) or "Apple Silicon"
        out.append(("Apple", chip, total_ram()))
    elif os.name == "nt":
        out += [g for g in windows_gpus() if g[0] != "NVIDIA" or not smi]
    elif sys.platform.startswith("linux"):
        for card in sorted(pathlib.Path("/sys/class/drm").glob("card[0-9]*/device")):
            vendor = (card / "vendor").read_text().strip() if (card / "vendor").exists() else ""
            vram = card / "mem_info_vram_total"
            if vendor == "0x1002" and vram.exists():   # AMD (amdgpu driver)
                out.append(("AMD", "AMD GPU", int(vram.read_text().strip())))
    return out


def windows_gpus():
    """Display adapters from the registry: the WMI AdapterRAM field is capped at 4 GB, the 64-bit size is not."""
    import winreg
    out, key = [], r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key)
    except OSError:
        return out
    for i in range(64):
        try:
            sub = winreg.OpenKey(root, winreg.EnumKey(root, i))
        except OSError:
            break
        try:
            name = winreg.QueryValueEx(sub, "DriverDesc")[0]
            mem = winreg.QueryValueEx(sub, "HardwareInformation.qwMemorySize")[0]
        except OSError:
            continue
        mem = int.from_bytes(mem, "little") if isinstance(mem, bytes) else int(mem)
        vendor = next((v for k, v in (("nvidia", "NVIDIA"), ("amd", "AMD"), ("radeon", "AMD"), ("intel", "Intel"))
                       if k in name.lower()), "other")
        if (vendor, name, mem) not in out:
            out.append((vendor, name, mem))
    return out


def label(vendor, name):
    return name if name.lower().startswith(vendor.lower()) else f"{vendor} {name}"


def model_budget(gpu_list, ram):
    """(bytes a model can use on the GPU, description). Integrated Intel graphics are not counted."""
    usable = [g for g in gpu_list if g[0] in ("NVIDIA", "AMD", "Apple")]
    if not usable:
        return 0, "no supported GPU: Ollama would run on the CPU (several times slower)"
    vendor, name, mem = max(usable, key=lambda g: g[2])
    if vendor == "Apple":
        share = 0.75 if mem > 36 * GB else 0.66   # macOS lets the GPU use about this much of unified memory
        return int(mem * share), f"{name}: {mem / GB:.0f} GB unified memory, about {mem * share / GB:.0f} GB usable by the GPU"
    return mem, f"{label(vendor, name)}: {mem / GB:.0f} GB"


# --- Ollama ------------------------------------------------------------------------------------------------------------

def ollama_binary():
    found = shutil.which("ollama")
    if found:
        return found
    for p in (pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
              pathlib.Path("/Applications/Ollama.app/Contents/Resources/ollama"), pathlib.Path("/usr/local/bin/ollama")):
        if p.is_file():
            return str(p)
    return None


def api(base, path, body=None, timeout=10):
    req = urllib.request.Request(base + path, json.dumps(body).encode() if body else None,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def is_embedding(m):
    return "embed" in m["name"] or m.get("details", {}).get("family", "") in ("bert", "nomic-bert")


def choose_model(installed, budget):
    """(catalog entry or None, installed?) for the best tested model that fits the GPU memory budget."""
    fits = [m for m in MODELS if m["recommended"] and m["need_gb"] * GB <= budget * 1.05]
    for m in fits:
        if m["name"] in installed:
            return m, True
    for m in MODELS:   # a recommended model that is installed but will partly run on the CPU
        if m["recommended"] and m["name"] in installed:
            return m, True
    return (fits[0] if fits else MODELS[0]), False


# --- the synthetic benchmark -------------------------------------------------------------------------------------------

BENCH_NOTE = """PATIENT: WHITCOMBE, ELEANOR J      DOB: 08/03/1958      MRN: 88310457
Larkspur Valley Cancer Institute - Millbrook
4417 Larkspur Ln, Millbrook TX 78990   Phone (555) 010-2398   Fax (555) 010-2399

Date of Service: 06/02/2015
Provider: Tobias Okonkwo, MD

FOLLOW-UP VISIT
Ms. Whitcombe is a 56 yo woman with ER+/PR-/HER2- invasive lobular carcinoma of the right breast, dx 2009, s/p
mastectomy. Bone mets on PET in 2014. On anastrozole + ribociclib (MONALEESA-2 regimen); Oncotype was 31 in 2009.
BRCA2 negative. CA 27-29 down to 41. Ki-67 12%. Kadcyla not indicated.
Her daughter Rosalind drives her to visits; Rosalind can be reached at r.whitcombe@example.com.
Surgical pathology (accession S15-04482) reviewed with Pemberton in pathology. Seen with Dr. Abernathy (radiation).

Electronically signed by: Tobias Okonkwo, MD on 06/03/2015
"""
# What the model is for: names and organizations, which no regex can find reliably.
BENCH_NAMES = [("Whitcombe", "patient surname"), ("Eleanor", "patient first name"), ("Okonkwo", "clinician full name"),
               ("Abernathy", "titled name (Dr. X)"), ("Pemberton", "bare surname"), ("Rosalind", "family member"),
               ("Larkspur Valley Cancer Institute", "facility")]
# Labelled identifiers the regex rules also catch: a model miss here is covered, but still worth knowing.
BENCH_OTHER = [("88310457", "MRN"), ("4417 Larkspur", "street address"), ("555) 010-2398", "phone"),
               ("r.whitcombe@example.com", "email"), ("S15-04482", "accession number")]
BENCH_CLINICAL = ["anastrozole", "ribociclib", "MONALEESA-2", "Oncotype", "BRCA2", "CA 27-29", "Ki-67", "Kadcyla"]


def bench(llm_cfg, model, rep):
    from .llm import LLMError, OllamaNER
    with tempfile.TemporaryDirectory() as tmp:
        ner = OllamaNER(dict(llm_cfg, model=model), pathlib.Path(tmp))
        try:
            ner.check()
            ner._call("Warm-up.")   # load the model before timing
            t = time.time()
            ents = ner._call(BENCH_NOTE)
            secs = time.time() - t
        except LLMError as e:
            rep.fail(f"benchmark: {e}")
            return
    if ents is None:
        rep.fail(f"benchmark: {model} returned unusable output")
        return
    found = [s.lower() for s, _ in ents]
    missing = lambda items: [d for k, d in items if not any(k.lower() in f for f in found)]
    flagged = [c for c in BENCH_CLINICAL if any(c.lower() in f for f in found)]
    for items, what, bad in ((BENCH_NAMES, "names and organizations", rep.warn),
                             (BENCH_OTHER, "labelled identifiers (the regex rules also catch these)", rep.info)):
        missed = missing(items)
        (rep.ok if not missed else bad)(f"benchmark {model}: {len(items) - len(missed)}/{len(items)} {what}"
                                        + (f"; missed: {', '.join(missed)}" if missed else ""))
    (rep.ok if not flagged else rep.warn)(f"benchmark {model}: {len(flagged)}/{len(BENCH_CLINICAL)} clinical terms wrongly flagged"
                                          + (f" ({', '.join(flagged)})" if flagged else ""))
    rep.info(f"benchmark {model}: {secs:.1f} s for {len(BENCH_NOTE)} characters "
             f"(about {secs * 7000 / len(BENCH_NOTE) / 60:.1f} min per 7-page note before caching)")


# --- the checks --------------------------------------------------------------------------------------------------------

def check_python(rep, cfg):
    rep.section("Python")
    v = sys.version_info
    (rep.ok if v >= (3, 11) else rep.fail)(f"Python {platform.python_version()} ({sys.executable})" + ("" if v >= (3, 11) else ": 3.11 or newer is required"))
    need = {"pdfplumber": "pdfplumber", "pypdfium2": "pypdfium2", "openpyxl": "openpyxl", "yaml": "PyYAML (reports)"}
    if any(s.get("ocr") for s in cfg.get("sources", [])):
        need["pytesseract"] = "pytesseract (OCR)"
    missing = [label for mod, label in need.items() if importlib.util.find_spec(mod) is None]
    if missing:
        rep.fail("missing packages: " + ", ".join(missing))
        rep.todo("pip install -e .   (or: pip install -r requirements.txt)")
    else:
        rep.ok("required packages installed")


def check_hardware(rep):
    rep.section("Hardware")
    ram = total_ram()
    rep.info(f"{platform.system()} {platform.release()} on {platform.machine()}, {ram / GB:.0f} GB RAM")
    found = gpus()
    for vendor, name, mem in found:
        rep.info(f"GPU: {label(vendor, name)}" + ("" if vendor == "Apple" else f", {mem / GB:.0f} GB"))
    budget, desc = model_budget(found, ram)
    (rep.ok if budget else rep.warn)(f"model memory: {desc}")
    return budget, ram


def check_ollama(rep, cfg, budget, ram, args):
    rep.section("Ollama (local model for name detection)")
    llm = cfg.get("llm", {})
    from .llm import LLMError, require_local
    try:
        base = require_local(llm.get("url", "http://localhost:11434"))
        rep.ok(f"llm.url is local ({base})")
    except LLMError as e:
        rep.fail(str(e))
        return
    exe = ollama_binary()
    (rep.ok if exe else rep.warn)("Ollama installed" if exe else "Ollama not found on this machine")
    try:
        version = api(base, "/api/version").get("version", "?")
        models = api(base, "/api/tags").get("models", [])
    except (urllib.error.URLError, OSError, ValueError):
        rep.fail(f"Ollama is not responding at {base}")
        rep.todo("install it from https://ollama.com/download, then start the Ollama app" if not exe else
                 "start the Ollama app (on Windows and macOS, the tray/menu-bar app; on Linux, the ollama service)")
        suggest(rep, None, budget, ram)
        return
    rep.ok(f"Ollama {version} running, {len(models)} model(s) installed")
    installed = {m["name"]: m for m in models}
    for c in MODELS:
        if c["name"] in installed:
            m = installed[c["name"]]
            rep.info(f"  {c['name']}: {m.get('size', 0) / GB:.1f} GB, tested, {'recommended' if c['recommended'] else 'not recommended'}: {c['note']}")
    others = [m for m in models if m["name"] not in {c["name"] for c in MODELS} and not is_embedding(m)]
    if others:
        rep.info(f"  {len(others)} other model(s), untested here; score one with  python -m pipeline doctor --bench --model NAME")
    pick, have = choose_model(installed, budget)
    configured = llm.get("model")
    if have:
        fits = pick["need_gb"] * GB <= budget * 1.05
        (rep.ok if fits else rep.warn)(f"best installed model: {pick['name']} ({pick['note']})"
                                       + ("" if fits else f"; needs about {pick['need_gb']} GB of GPU memory, so part of it will run on the CPU (slower)"))
        if configured != pick["name"]:
            rep.warn(f"configured model is {configured!r}")
            rep.todo(f'set  [llm] model = "{pick["name"]}"  in config/local.toml')
    else:
        rep.warn("no tested, recommended model is installed")
        suggest(rep, pick, budget, ram)
    if configured and configured not in installed:
        rep.fail(f"the configured model {configured!r} is not installed")
        rep.todo(f"ollama pull {configured}   (or choose another model in config/local.toml)")
    running = {m["name"]: m for m in api(base, "/api/ps").get("models", [])} if models else {}
    if configured in running:
        m = running[configured]
        share = m.get("size_vram", 0) / max(m.get("size", 1), 1)
        (rep.ok if share > 0.95 else rep.warn)(f"{configured} is loaded, {share:.0%} on the GPU"
                                               + ("" if share > 0.95 else ": runs slower; if this GPU should fit it, restart the Ollama app"))
    if args.bench:
        bench(llm, args.model or (configured if configured in installed else pick["name"]), rep)


def suggest(rep, pick, budget, ram):
    pick = pick or next((m for m in MODELS if m["recommended"] and m["need_gb"] * GB <= budget * 1.05), MODELS[0])
    size = f" (about {pick['download_gb']} GB download)" if pick.get("download_gb") else ""
    rep.todo(f"suggested model: {pick['name']}, {pick['note']}{size}. To install it yourself:  ollama pull {pick['name']}")
    if pick["need_gb"] * GB > budget:
        where = "the CPU" if not budget else "the CPU for the part that does not fit on the GPU"
        rep.todo(f"it needs about {pick['need_gb']} GB of GPU memory; this machine will use {where}. "
                 + ("That works but is several times slower; caching makes reruns fast."
                    if ram >= 16 * GB else "With under 16 GB of RAM it may not run at all."))
        rep.todo("smaller models are faster but missed names in testing; don't trade recall for speed here")


def check_tools(rep, cfg):
    rep.section("Optional tools")
    from .ocr import find_tesseract
    ocr_needed = any(s.get("ocr") for s in cfg.get("sources", []))
    tess = cfg.get("ocr", {}).get("tesseract") or find_tesseract()
    v = run_cmd([tess, "--version"])
    if v:
        rep.ok(f"Tesseract {v.splitlines()[0].split()[-1]} (OCR for scanned PDFs)")
    else:
        (rep.fail if ocr_needed else rep.info)("Tesseract not found" + (": a source has ocr = true" if ocr_needed else " (only needed for scanned PDFs)"))
        rep.todo("Windows: https://github.com/UB-Mannheim/tesseract/wiki   macOS: brew install tesseract   Linux: apt install tesseract-ocr")
    node = run_cmd(["node", "--version"])
    docx = (ROOT / "reports" / "node_modules" / "docx").exists()
    if node and docx:
        rep.ok(f"Node {node} with docx (editable Word emergency summary)")
    else:
        rep.info("Word emergency summary unavailable: " + ("Node.js not found" if not node else "docx not installed"))
        rep.todo("install Node.js (https://nodejs.org), then run  npm install  in reports/" if not node else "run  npm install  in reports/")
    try:
        from reports.common import find_browser
        browser = find_browser()
    except Exception:
        browser = None
    (rep.ok if browser else rep.warn)(f"PDF printing browser: {browser}" if browser else
                                      "no Chrome, Edge or Chromium found: reports build as HTML only")
    if not browser:
        rep.todo("install Google Chrome or Chromium, or set PCR_BROWSER to a Chromium-based browser")


def check_data(rep, cfg, paths):
    rep.section("Configuration and data")
    local = ROOT / "config" / "local.toml"
    (rep.ok if local.exists() else rep.info)("config/local.toml present" if local.exists() else
                                             "no config/local.toml: using the example source in config/pipeline.toml")
    for s in cfg.get("sources", []):
        d = ROOT / s["path"]
        if not d.is_dir():
            rep.warn(f"source {s['name']!r}: folder {s['path']} does not exist")
            continue
        files = [p for p in d.rglob("*") if p.is_file()]
        kinds = {}
        for p in files:
            kinds[p.suffix.lower() or "(none)"] = kinds.get(p.suffix.lower() or "(none)", 0) + 1
        summary = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
        (rep.ok if files else rep.warn)(f"source {s['name']!r}: {len(files)} file(s)" + (f" ({summary})" if files else ""))
    (rep.ok if paths.identifiers.exists() else rep.warn)(
        "private/identifiers.toml present" if paths.identifiers.exists() else "private/identifiers.toml missing")
    if not paths.identifiers.exists():
        rep.todo("python -m pipeline init, then fill it in yourself (it holds the patient's names, DOB and record numbers)")
    settings = ROOT / ".claude" / "settings.json"
    guarded = settings.exists() and all(x in settings.read_text(encoding="utf-8") for x in ("Sources/", "private/"))
    (rep.ok if guarded else rep.warn)("Claude Code is denied access to Sources/ and private/ (.claude/settings.json)" if guarded else
                                      ".claude/settings.json does not deny Sources/ and private/")


def doctor(cfg, paths, args):
    rep = Report()
    print("PatientCentricRecords doctor: checks only; nothing is installed or downloaded.")
    check_python(rep, cfg)
    budget, ram = check_hardware(rep)
    check_ollama(rep, cfg, budget, ram, args)
    check_tools(rep, cfg)
    check_data(rep, cfg, paths)
    print(f"\n{rep.fails} problem(s), {rep.warns} warning(s).")
    return 1 if rep.fails else 0
