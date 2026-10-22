"""Local OCR (Tesseract) for scanned PDF pages and image files. Results are cached under private/cache/ocr/.

Only used for sources marked `ocr = true`. A PDF page that already has a text layer keeps it;
the rest are rendered (pypdfium2), orientation-corrected (Tesseract OSD) and recognised.
Image files (PNG, JPEG, TIFF) have no text layer, so every frame is recognised.
Nothing leaves the machine. OCR text is de-identified like any other text, plus fuzzy name
matching (fuzzy.py) because OCR misreads letters ("Th0rnbury").
"""
import json
import os
import re
import shutil

TEXT_LAYER_MIN = 50
IMAGE_MIN_WIDTH = 2000   # pixels; narrower images (screenshots) are enlarged before recognition
WINDOWS_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"   # the Windows installer does not add itself to PATH


class OCRError(RuntimeError):
    pass


def find_tesseract():
    """The tesseract executable: on PATH, else the default Windows install location, else just the name."""
    found = shutil.which("tesseract")
    if found:
        return found
    if os.name == "nt" and os.path.exists(WINDOWS_DEFAULT):
        return WINDOWS_DEFAULT
    return "tesseract"


class OCR:
    def __init__(self, cfg, cache_dir):
        import pytesseract
        self.tess = pytesseract
        self.tess.pytesseract.tesseract_cmd = cfg.get("tesseract") or find_tesseract()
        self.dpi = cfg.get("dpi", 300)
        self.lang = cfg.get("lang", "eng")
        self.cache = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.pages_done = self.cache_hits = 0
        try:
            self.tess.get_tesseract_version()
        except Exception:
            raise OCRError("Tesseract is not available; install it or set [ocr] tesseract in config/local.toml") from None

    def page(self, pdf_bytes, sha, index):
        """A PDF page -> (text, mean word confidence 0-100)"""
        def render():
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(pdf_bytes)
            img = pdf[index].render(scale=self.dpi / 72).to_pil().convert("L")
            pdf.close()
            return img
        return self._cached(sha, index, render)

    def image(self, img_bytes, sha, index):
        """A frame of an image file (PNG, JPEG, or a page of a multi-page TIFF) -> (text, mean word confidence 0-100)"""
        def load():
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(img_bytes))
            img.seek(index)
            img = img.convert("L")
            if img.width < IMAGE_MIN_WIDTH:   # screenshots are ~96 dpi; Tesseract reads small print better enlarged
                f = IMAGE_MIN_WIDTH / img.width
                img = img.resize((round(img.width * f), round(img.height * f)), Image.LANCZOS)
            return img
        return self._cached(sha, index, load)

    def _cached(self, sha, index, get_image):
        cached = self.cache / f"{sha[:16]}-{index}.json"
        if cached.exists():
            self.cache_hits += 1
            d = json.loads(cached.read_text(encoding="utf-8"))
            return d["text"], d["conf"]
        img = get_image()
        try:   # orientation: rotate scans that were fed sideways or upside down
            osd = self.tess.image_to_osd(img, output_type=self.tess.Output.DICT)
            if osd.get("rotate"):
                img = img.rotate(-osd["rotate"], expand=True)
        except Exception:
            pass   # too little text for OSD; keep as is
        data = self.tess.image_to_data(img, lang=self.lang, config="--psm 3", output_type=self.tess.Output.DICT)
        lines, confs, key = {}, [], None
        for i, word in enumerate(data["text"]):
            if not word.strip():
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(word)
            c = float(data["conf"][i])
            if c >= 0:
                confs.append(c)
        text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
        conf = round(sum(confs) / len(confs), 1) if confs else 0.0
        cached.write_text(json.dumps({"text": text, "conf": conf}), encoding="utf-8")
        self.pages_done += 1
        return text, conf
