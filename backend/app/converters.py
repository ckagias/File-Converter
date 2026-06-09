import csv
import io
import subprocess
import tarfile
import traceback
import zipfile
from pathlib import Path

import cairosvg
import ffmpeg
import py7zr
from pdf2docx import Converter as PDF2DocxConverter
from pdf2image import convert_from_path
from PIL import Image
from pydub import AudioSegment
import openpyxl
import PyPDF2

UPLOAD_DIR = Path("/app/uploads")
OUTPUT_DIR = Path("/app/outputs")

SUPPORTED_CONVERSIONS: dict[str, list[str]] = {
    # documents
    "docx": ["pdf", "txt", "html"],
    "pdf":  ["docx", "txt", "jpg", "png"],
    "pptx": ["pdf", "jpg", "png"],
    "xlsx": ["pdf", "csv"],
    "odt":  ["pdf"],
    # images
    "jpg":  ["png", "webp", "bmp", "tiff", "pdf"],
    "jpeg": ["png", "webp", "bmp", "tiff", "pdf"],
    "png":  ["jpg", "webp", "bmp", "tiff", "pdf"],
    "webp": ["jpg", "png", "bmp", "tiff", "pdf"],
    "bmp":  ["jpg", "png", "webp", "tiff", "pdf"],
    "tiff": ["jpg", "png", "webp", "bmp", "pdf"],
    "svg":  ["png", "jpg"],
    "ico":  ["png"],
    # audio
    "mp3":  ["wav", "ogg", "flac", "aac", "m4a"],
    "wav":  ["mp3", "ogg", "flac", "aac", "m4a"],
    "ogg":  ["mp3", "wav", "flac", "aac", "m4a"],
    "flac": ["mp3", "wav", "ogg", "aac", "m4a"],
    "aac":  ["mp3", "wav", "ogg", "flac", "m4a"],
    "m4a":  ["mp3", "wav", "ogg", "flac", "aac"],
    # video
    "mp4":  ["mkv", "avi", "mov", "webm", "mp3"],
    "mkv":  ["mp4", "avi", "mov", "webm", "mp3"],
    "avi":  ["mp4", "mkv", "mov", "webm"],
    "mov":  ["mp4", "mkv", "avi", "webm"],
    "webm": ["mp4", "mkv", "avi", "mov"],
    # archives
    "zip":  ["7z", "tar.gz"],
    "7z":   ["zip"],
    "gz":   ["zip"],  # tar.gz detected by extension
}

_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "tiff", "ico", "svg"}
_AUDIO_EXTS = {"mp3", "wav", "ogg", "flac", "aac", "m4a"}
_VIDEO_EXTS = {"mp4", "mkv", "avi", "mov", "webm"}
_ARCHIVE_EXTS = {"zip", "7z", "gz", "tar.gz"}


def _output_name(stored: str, ext: str) -> str:
    return stored.rsplit(".", 1)[0] + "." + ext.lstrip(".")


def _libreoffice_convert(input_path: Path, target_ext: str, output_dir: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", target_ext,
             "--outdir", str(output_dir), str(input_path)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(result.stderr)
            return False, ""
        output_path = output_dir / (input_path.stem + "." + target_ext)
        if not output_path.exists():
            return False, ""
        return True, output_path.name
    except Exception:
        traceback.print_exc()
        return False, ""


# ── Document converters ──────────────────────────────────────────────────────

def _convert_docx(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, target_ext)
        out_path = OUTPUT_DIR / out_name
        ok, lo_name = _libreoffice_convert(input_path, target_ext, OUTPUT_DIR)
        if not ok:
            return False, ""
        # LibreOffice may name the file differently; rename to our convention
        lo_path = OUTPUT_DIR / lo_name
        if lo_path != out_path:
            lo_path.rename(out_path)
        return True, out_name
    except Exception:
        traceback.print_exc()
        out_path = OUTPUT_DIR / _output_name(stored, target_ext)
        if out_path.exists():
            out_path.unlink()
        return False, ""


def _convert_pdf_to_docx(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "docx")
        out_path = OUTPUT_DIR / out_name
        cv = PDF2DocxConverter(str(input_path))
        cv.convert(str(out_path))
        cv.close()
        return True, out_name
    except Exception:
        traceback.print_exc()
        out_path = OUTPUT_DIR / _output_name(stored, "docx")
        if out_path.exists():
            out_path.unlink()
        return False, ""


def _convert_pdf_to_txt(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "txt")
        out_path = OUTPUT_DIR / out_name
        reader = PyPDF2.PdfReader(str(input_path))
        text = "\n".join(
            page.extract_text() or "" for page in reader.pages
        )
        out_path.write_text(text, encoding="utf-8")
        return True, out_name
    except Exception:
        traceback.print_exc()
        out_path = OUTPUT_DIR / _output_name(stored, "txt")
        if out_path.exists():
            out_path.unlink()
        return False, ""


def _convert_pdf_to_image(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        pages = convert_from_path(str(input_path))
        pil_fmt = "JPEG" if target_ext in ("jpg", "jpeg") else target_ext.upper()
        if len(pages) == 1:
            out_name = _output_name(stored, target_ext)
            out_path = OUTPUT_DIR / out_name
            pages[0].save(str(out_path), pil_fmt)
            return True, out_name
        # multi-page: pack into zip
        zip_name = _output_name(stored, "zip")
        zip_path = OUTPUT_DIR / zip_name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, page in enumerate(pages):
                buf = io.BytesIO()
                page.save(buf, pil_fmt)
                zf.writestr(f"page_{i + 1:04d}.{target_ext}", buf.getvalue())
        return True, zip_name
    except Exception:
        traceback.print_exc()
        for ext in (target_ext, "zip"):
            p = OUTPUT_DIR / _output_name(stored, ext)
            if p.exists():
                p.unlink()
        return False, ""


def _convert_pptx_to_pdf(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "pdf")
        ok, lo_name = _libreoffice_convert(input_path, "pdf", OUTPUT_DIR)
        if not ok:
            return False, ""
        lo_path = OUTPUT_DIR / lo_name
        out_path = OUTPUT_DIR / out_name
        if lo_path != out_path:
            lo_path.rename(out_path)
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, "pdf")
        if p.exists():
            p.unlink()
        return False, ""


def _convert_pptx_to_image(stored: str, target_ext: str) -> tuple[bool, str]:
    # convert to pdf first, then pdf to image
    try:
        input_path = UPLOAD_DIR / stored
        ok, pdf_name = _libreoffice_convert(input_path, "pdf", OUTPUT_DIR)
        if not ok:
            return False, ""
        # reuse pdf-to-image handler treating the intermediate pdf as uploaded
        # copy pdf to uploads temporarily
        tmp_stored = pdf_name
        (UPLOAD_DIR / tmp_stored).write_bytes((OUTPUT_DIR / pdf_name).read_bytes())
        ok2, out_name = _convert_pdf_to_image(tmp_stored, target_ext)
        (UPLOAD_DIR / tmp_stored).unlink(missing_ok=True)
        (OUTPUT_DIR / pdf_name).unlink(missing_ok=True)
        return ok2, out_name
    except Exception:
        traceback.print_exc()
        return False, ""


def _convert_xlsx_to_pdf(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "pdf")
        ok, lo_name = _libreoffice_convert(input_path, "pdf", OUTPUT_DIR)
        if not ok:
            return False, ""
        lo_path = OUTPUT_DIR / lo_name
        out_path = OUTPUT_DIR / out_name
        if lo_path != out_path:
            lo_path.rename(out_path)
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, "pdf")
        if p.exists():
            p.unlink()
        return False, ""


def _convert_xlsx_to_csv(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "csv")
        out_path = OUTPUT_DIR / out_name
        wb = openpyxl.load_workbook(str(input_path), read_only=True, data_only=True)
        ws = wb.active
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in ws.iter_rows(values_only=True):
                writer.writerow([("" if v is None else v) for v in row])
        wb.close()
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, "csv")
        if p.exists():
            p.unlink()
        return False, ""


def _convert_odt_to_pdf(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "pdf")
        ok, lo_name = _libreoffice_convert(input_path, "pdf", OUTPUT_DIR)
        if not ok:
            return False, ""
        lo_path = OUTPUT_DIR / lo_name
        out_path = OUTPUT_DIR / out_name
        if lo_path != out_path:
            lo_path.rename(out_path)
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, "pdf")
        if p.exists():
            p.unlink()
        return False, ""


# ── Image converters ─────────────────────────────────────────────────────────

def _pil_save_fmt(ext: str) -> str:
    mapping = {"jpg": "JPEG", "jpeg": "JPEG", "tiff": "TIFF"}
    return mapping.get(ext, ext.upper())


def _convert_image(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, target_ext)
        out_path = OUTPUT_DIR / out_name
        img = Image.open(str(input_path))
        # JPEG doesn't support alpha
        if target_ext in ("jpg", "jpeg") and img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        if target_ext == "pdf":
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            img.save(str(out_path), "PDF", resolution=100)
        else:
            img.save(str(out_path), _pil_save_fmt(target_ext))
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, target_ext)
        if p.exists():
            p.unlink()
        return False, ""


def _convert_svg(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, target_ext)
        out_path = OUTPUT_DIR / out_name
        png_bytes = cairosvg.svg2png(url=str(input_path))
        if target_ext == "png":
            out_path.write_bytes(png_bytes)
        else:
            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            img.save(str(out_path), _pil_save_fmt(target_ext))
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, target_ext)
        if p.exists():
            p.unlink()
        return False, ""


# ── Audio converters ─────────────────────────────────────────────────────────

_PYDUB_FORMAT = {
    "mp3": "mp3", "wav": "wav", "ogg": "ogg",
    "flac": "flac", "aac": "adts", "m4a": "mp4",
}


def _convert_audio(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        src_ext = stored.rsplit(".", 1)[-1].lower()
        out_name = _output_name(stored, target_ext)
        out_path = OUTPUT_DIR / out_name
        audio = AudioSegment.from_file(str(input_path), format=_PYDUB_FORMAT.get(src_ext, src_ext))
        audio.export(str(out_path), format=_PYDUB_FORMAT.get(target_ext, target_ext))
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, target_ext)
        if p.exists():
            p.unlink()
        return False, ""


# ── Video converters ─────────────────────────────────────────────────────────

def _convert_video(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, target_ext)
        out_path = OUTPUT_DIR / out_name
        if target_ext == "mp3":
            # extract audio only
            (
                ffmpeg
                .input(str(input_path))
                .output(str(out_path), acodec="libmp3lame", vn=None)
                .overwrite_output()
                .run(quiet=True)
            )
        else:
            (
                ffmpeg
                .input(str(input_path))
                .output(str(out_path))
                .overwrite_output()
                .run(quiet=True)
            )
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, target_ext)
        if p.exists():
            p.unlink()
        return False, ""


# ── Archive converters ────────────────────────────────────────────────────────

def _repack_zip_to_7z(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "7z")
        out_path = OUTPUT_DIR / out_name
        with zipfile.ZipFile(str(input_path), "r") as zf:
            with py7zr.SevenZipFile(str(out_path), "w") as sz:
                for item in zf.infolist():
                    with zf.open(item) as f:
                        sz.writef(f, item.filename)
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, "7z")
        if p.exists():
            p.unlink()
        return False, ""


def _repack_zip_to_targz(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "tar.gz")
        out_path = OUTPUT_DIR / out_name
        with zipfile.ZipFile(str(input_path), "r") as zf:
            with tarfile.open(str(out_path), "w:gz") as tf:
                for item in zf.infolist():
                    with zf.open(item) as f:
                        data = f.read()
                        info = tarfile.TarInfo(name=item.filename)
                        info.size = len(data)
                        tf.addfile(info, io.BytesIO(data))
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, "tar.gz")
        if p.exists():
            p.unlink()
        return False, ""


def _repack_7z_to_zip(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "zip")
        out_path = OUTPUT_DIR / out_name
        with py7zr.SevenZipFile(str(input_path), "r") as sz:
            members = sz.readall()
        with zipfile.ZipFile(str(out_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for name, buf in members.items():
                zf.writestr(name, buf.read())
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, "zip")
        if p.exists():
            p.unlink()
        return False, ""


def _repack_targz_to_zip(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "zip")
        out_path = OUTPUT_DIR / out_name
        with tarfile.open(str(input_path), "r:gz") as tf:
            with zipfile.ZipFile(str(out_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for member in tf.getmembers():
                    if member.isfile():
                        f = tf.extractfile(member)
                        if f:
                            zf.writestr(member.name, f.read())
        return True, out_name
    except Exception:
        traceback.print_exc()
        p = OUTPUT_DIR / _output_name(stored, "zip")
        if p.exists():
            p.unlink()
        return False, ""


# ── Dispatcher ────────────────────────────────────────────────────────────────

def handle_conversion(stored_filename: str, target_format: str) -> tuple[bool, str]:
    src_ext = stored_filename.rsplit(".", 1)[-1].lower() if "." in stored_filename else ""
    tgt = target_format.lower().lstrip(".")

    # documents
    if src_ext == "docx":
        return _convert_docx(stored_filename, tgt)
    if src_ext == "pdf":
        if tgt == "docx":
            return _convert_pdf_to_docx(stored_filename, tgt)
        if tgt == "txt":
            return _convert_pdf_to_txt(stored_filename, tgt)
        if tgt in ("jpg", "jpeg", "png"):
            return _convert_pdf_to_image(stored_filename, tgt)
    if src_ext == "pptx":
        if tgt == "pdf":
            return _convert_pptx_to_pdf(stored_filename, tgt)
        if tgt in ("jpg", "jpeg", "png"):
            return _convert_pptx_to_image(stored_filename, tgt)
    if src_ext == "xlsx":
        if tgt == "pdf":
            return _convert_xlsx_to_pdf(stored_filename, tgt)
        if tgt == "csv":
            return _convert_xlsx_to_csv(stored_filename, tgt)
    if src_ext == "odt":
        return _convert_odt_to_pdf(stored_filename, tgt)

    # images
    if src_ext == "svg":
        return _convert_svg(stored_filename, tgt)
    if src_ext in _IMAGE_EXTS:
        return _convert_image(stored_filename, tgt)

    # audio
    if src_ext in _AUDIO_EXTS:
        return _convert_audio(stored_filename, tgt)

    # video
    if src_ext in _VIDEO_EXTS:
        return _convert_video(stored_filename, tgt)

    # archives
    if src_ext == "zip":
        if tgt == "7z":
            return _repack_zip_to_7z(stored_filename, tgt)
        if tgt == "tar.gz":
            return _repack_zip_to_targz(stored_filename, tgt)
    if src_ext == "7z":
        return _repack_7z_to_zip(stored_filename, tgt)
    if src_ext == "gz":
        return _repack_targz_to_zip(stored_filename, tgt)

    print(f"No handler for {src_ext} -> {tgt}")
    return False, ""