import csv
import io
import logging
import subprocess
import tarfile
import unicodedata
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

from app.config import settings

logger = logging.getLogger(__name__)

UPLOAD_DIR = settings.upload_dir
OUTPUT_DIR = settings.output_dir

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

# Category size limits used by the upload endpoint
CATEGORY_SIZE_LIMITS_MB: dict[str, int] = {
    "image":    50,
    "document": 100,
    "audio":    200,
    "video":    2000,
    "archive":  500,
}

EXT_CATEGORY: dict[str, str] = {
    "jpg": "image", "jpeg": "image", "png": "image", "webp": "image",
    "bmp": "image", "tiff": "image", "svg": "image", "ico": "image",
    "pdf": "document", "docx": "document", "pptx": "document",
    "xlsx": "document", "odt": "document", "txt": "document",
    "mp3": "audio", "wav": "audio", "ogg": "audio",
    "flac": "audio", "aac": "audio", "m4a": "audio",
    "mp4": "video", "mkv": "video", "avi": "video", "mov": "video", "webm": "video",
    "zip": "archive", "7z": "archive", "gz": "archive",
}


_ZIP_BOMB_LIMIT = 4 * 1024 * 1024 * 1024  # 4 GB uncompressed

MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "pdf":  [b"%PDF"],
    "jpg":  [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "png":  [b"\x89PNG\r\n\x1a\n"],
    "mp3":  [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"],
    "mp4":  [b"\x00\x00\x00\x18ftyp", b"\x00\x00\x00\x20ftyp",
             b"\x00\x00\x00\x1cftyp", b"ftyp"],
    # docx/pptx/xlsx and zip/7z share PK header
    "docx": [b"PK\x03\x04"],
    "pptx": [b"PK\x03\x04"],
    "xlsx": [b"PK\x03\x04"],
    "zip":  [b"PK\x03\x04"],
    "7z":   [b"7z\xbc\xaf\x27\x1c"],
}


def _safe_archive_member(name: str, dest_dir: Path) -> Path:
    """Resolve member path and raise if it escapes dest_dir (Zip Slip guard)."""
    target = (dest_dir / name).resolve()
    if not str(target).startswith(str(dest_dir.resolve())):
        raise ValueError(f"Unsafe archive member: {name!r}")
    return target


def _check_zip_bomb(zf: zipfile.ZipFile) -> None:
    total = sum(i.file_size for i in zf.infolist())
    if total > _ZIP_BOMB_LIMIT:
        raise ValueError(f"ZIP bomb detected: uncompressed size {total} exceeds limit")


def _check_7z_bomb(sz: py7zr.SevenZipFile) -> None:
    total = sum(
        (info.uncompressed or 0) for info in sz.list() if not info.is_directory
    )
    if total > _ZIP_BOMB_LIMIT:
        raise ValueError(f"ZIP bomb detected: uncompressed size {total} exceeds limit")


def validate_magic_bytes(path: Path, ext: str) -> None:
    """Raise ValueError if the file's magic bytes don't match the declared extension."""
    sigs = MAGIC_SIGNATURES.get(ext.lower())
    if not sigs:
        return
    header = path.read_bytes()[:32]
    if not any(header.startswith(s) for s in sigs):
        raise ValueError(f"File content does not match declared extension .{ext}")


def _output_name(stored: str, ext: str) -> str:
    return stored.rsplit(".", 1)[0] + "." + ext.lstrip(".")


def _libreoffice_to_pdf(input_path: Path) -> tuple[bool, str]:
    """Convert any LibreOffice-supported file to PDF and return (ok, output_name)."""
    try:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf",
             "--outdir", str(OUTPUT_DIR), str(input_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            logger.error("LibreOffice stderr: %s", result.stderr)
            return False, ""
        output_path = OUTPUT_DIR / (input_path.stem + ".pdf")
        if not output_path.exists():
            return False, ""
        return True, output_path.name
    except Exception:
        logger.exception("LibreOffice conversion failed for %s", input_path)
        return False, ""


def _libreoffice_convert(input_path: Path, target_ext: str, output_dir: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", target_ext,
             "--outdir", str(output_dir), str(input_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            logger.error("LibreOffice stderr: %s", result.stderr)
            return False, ""
        output_path = output_dir / (input_path.stem + "." + target_ext)
        if not output_path.exists():
            return False, ""
        return True, output_path.name
    except Exception:
        logger.exception("LibreOffice conversion failed for %s", input_path)
        return False, ""


# Document converters

def _convert_docx(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, target_ext)
        out_path = OUTPUT_DIR / out_name
        ok, lo_name = _libreoffice_convert(input_path, target_ext, OUTPUT_DIR)
        if not ok:
            return False, ""
        lo_path = OUTPUT_DIR / lo_name
        if lo_path != out_path:
            lo_path.rename(out_path)
        return True, out_name
    except Exception:
        logger.exception("docx conversion failed: %s -> %s", stored, target_ext)
        _cleanup(OUTPUT_DIR / _output_name(stored, target_ext))
        return False, ""


def _convert_via_libreoffice_to_pdf(stored: str) -> tuple[bool, str]:
    """Generic handler for docx/pptx/xlsx/odt -> pdf via LibreOffice."""
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "pdf")
        out_path = OUTPUT_DIR / out_name
        ok, lo_name = _libreoffice_to_pdf(input_path)
        if not ok:
            return False, ""
        lo_path = OUTPUT_DIR / lo_name
        if lo_path != out_path:
            lo_path.rename(out_path)
        return True, out_name
    except Exception:
        logger.exception("LibreOffice->pdf failed: %s", stored)
        _cleanup(OUTPUT_DIR / _output_name(stored, "pdf"))
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
        logger.exception("pdf->docx failed: %s", stored)
        _cleanup(OUTPUT_DIR / _output_name(stored, "docx"))
        return False, ""


def _convert_pdf_to_txt(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "txt")
        out_path = OUTPUT_DIR / out_name
        reader = PyPDF2.PdfReader(str(input_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        out_path.write_text(text, encoding="utf-8")
        return True, out_name
    except Exception:
        logger.exception("pdf->txt failed: %s", stored)
        _cleanup(OUTPUT_DIR / _output_name(stored, "txt"))
        return False, ""


def _convert_pdf_to_image(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        pages = convert_from_path(str(input_path))
        pil_fmt = "JPEG" if target_ext in ("jpg", "jpeg") else target_ext.upper()
        if len(pages) == 1:
            out_name = _output_name(stored, target_ext)
            pages[0].save(str(OUTPUT_DIR / out_name), pil_fmt)
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
        logger.exception("pdf->image failed: %s -> %s", stored, target_ext)
        for ext in (target_ext, "zip"):
            _cleanup(OUTPUT_DIR / _output_name(stored, ext))
        return False, ""


def _convert_pptx_to_image(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        ok, pdf_name = _libreoffice_to_pdf(input_path)
        if not ok:
            return False, ""
        # reuse pdf-to-image handler: copy intermediate pdf to uploads temporarily
        tmp_stored = pdf_name
        (UPLOAD_DIR / tmp_stored).write_bytes((OUTPUT_DIR / pdf_name).read_bytes())
        ok2, out_name = _convert_pdf_to_image(tmp_stored, target_ext)
        (UPLOAD_DIR / tmp_stored).unlink(missing_ok=True)
        (OUTPUT_DIR / pdf_name).unlink(missing_ok=True)
        return ok2, out_name
    except Exception:
        logger.exception("pptx->image failed: %s -> %s", stored, target_ext)
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
        logger.exception("xlsx->csv failed: %s", stored)
        _cleanup(OUTPUT_DIR / _output_name(stored, "csv"))
        return False, ""


# Image converters

def _pil_save_fmt(ext: str) -> str:
    return {"jpg": "JPEG", "jpeg": "JPEG", "tiff": "TIFF"}.get(ext, ext.upper())


def _convert_image(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, target_ext)
        out_path = OUTPUT_DIR / out_name
        img = Image.open(str(input_path))
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
        logger.exception("image conversion failed: %s -> %s", stored, target_ext)
        _cleanup(OUTPUT_DIR / _output_name(stored, target_ext))
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
        logger.exception("svg conversion failed: %s -> %s", stored, target_ext)
        _cleanup(OUTPUT_DIR / _output_name(stored, target_ext))
        return False, ""


# Audio converters

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
        logger.exception("audio conversion failed: %s -> %s", stored, target_ext)
        _cleanup(OUTPUT_DIR / _output_name(stored, target_ext))
        return False, ""


# Video converters

def _convert_video(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, target_ext)
        out_path = OUTPUT_DIR / out_name

        stream = ffmpeg.input(str(input_path))
        if target_ext == "mp3":
            stream = stream.output(str(out_path), acodec="libmp3lame", vn=None)
        else:
            stream = stream.output(str(out_path))

        # ffmpeg-python's .run() has no timeout parameter, so compile the
        # argument list and hand it to subprocess where we can set one.
        # 30 min matches the Celery task_time_limit.
        args = stream.overwrite_output().compile()
        result = subprocess.run(args, timeout=1800, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode(errors="replace")[:512])

        return True, out_name
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timed out for %s", stored)
        _cleanup(OUTPUT_DIR / _output_name(stored, target_ext))
        return False, ""
    except Exception:
        logger.exception("video conversion failed: %s -> %s", stored, target_ext)
        _cleanup(OUTPUT_DIR / _output_name(stored, target_ext))
        return False, ""


# Archive converters

def _repack_zip_to_7z(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "7z")
        out_path = OUTPUT_DIR / out_name
        with zipfile.ZipFile(str(input_path), "r") as zf:
            _check_zip_bomb(zf)
            with py7zr.SevenZipFile(str(out_path), "w") as sz:
                for item in zf.infolist():
                    _safe_archive_member(item.filename, OUTPUT_DIR)
                    with zf.open(item) as f:
                        sz.writef(f, item.filename)
        return True, out_name
    except Exception:
        logger.exception("zip->7z failed: %s", stored)
        _cleanup(OUTPUT_DIR / _output_name(stored, "7z"))
        return False, ""


def _repack_zip_to_targz(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "tar.gz")
        out_path = OUTPUT_DIR / out_name
        with zipfile.ZipFile(str(input_path), "r") as zf:
            _check_zip_bomb(zf)
            with tarfile.open(str(out_path), "w:gz") as tf:
                for item in zf.infolist():
                    _safe_archive_member(item.filename, OUTPUT_DIR)
                    with zf.open(item) as f:
                        data = f.read()
                        info = tarfile.TarInfo(name=item.filename)
                        info.size = len(data)
                        tf.addfile(info, io.BytesIO(data))
        return True, out_name
    except Exception:
        logger.exception("zip->tar.gz failed: %s", stored)
        _cleanup(OUTPUT_DIR / _output_name(stored, "tar.gz"))
        return False, ""


def _repack_7z_to_zip(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        import tempfile
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "zip")
        out_path = OUTPUT_DIR / out_name
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with py7zr.SevenZipFile(str(input_path), "r") as sz:
                _check_7z_bomb(sz)
                sz.extractall(path=tmp_dir)
            with zipfile.ZipFile(str(out_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for extracted in tmp_path.rglob("*"):
                    if extracted.is_file():
                        arcname = extracted.relative_to(tmp_path).as_posix()
                        _safe_archive_member(arcname, OUTPUT_DIR)
                        zf.write(extracted, arcname)
        return True, out_name
    except Exception:
        logger.exception("7z->zip failed: %s", stored)
        _cleanup(OUTPUT_DIR / _output_name(stored, "zip"))
        return False, ""


def _repack_targz_to_zip(stored: str, target_ext: str) -> tuple[bool, str]:
    try:
        input_path = UPLOAD_DIR / stored
        out_name = _output_name(stored, "zip")
        out_path = OUTPUT_DIR / out_name
        with tarfile.open(str(input_path), "r:gz") as tf:
            total = sum(m.size for m in tf.getmembers() if m.isfile())
            if total > _ZIP_BOMB_LIMIT:
                raise ValueError(f"ZIP bomb detected: uncompressed size {total} exceeds limit")
            with zipfile.ZipFile(str(out_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for member in tf.getmembers():
                    if member.isfile():
                        _safe_archive_member(member.name, OUTPUT_DIR)
                        f = tf.extractfile(member)
                        if f:
                            zf.writestr(member.name, f.read())
        return True, out_name
    except Exception:
        logger.exception("tar.gz->zip failed: %s", stored)
        _cleanup(OUTPUT_DIR / _output_name(stored, "zip"))
        return False, ""


# Helpers

def _cleanup(path: Path) -> None:
    path.unlink(missing_ok=True)


# Dispatcher

def handle_conversion(stored_filename: str, target_format: str) -> tuple[bool, str]:
    src_ext = stored_filename.rsplit(".", 1)[-1].lower() if "." in stored_filename else ""
    tgt = target_format.lower().lstrip(".")

    try:
        validate_magic_bytes(UPLOAD_DIR / stored_filename, src_ext)
    except ValueError as exc:
        logger.warning("Magic byte check failed for %s: %s", stored_filename, exc)
        return False, ""

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
            return _convert_via_libreoffice_to_pdf(stored_filename)
        if tgt in ("jpg", "jpeg", "png"):
            return _convert_pptx_to_image(stored_filename, tgt)
    if src_ext == "xlsx":
        if tgt == "pdf":
            return _convert_via_libreoffice_to_pdf(stored_filename)
        if tgt == "csv":
            return _convert_xlsx_to_csv(stored_filename, tgt)
    if src_ext == "odt":
        return _convert_via_libreoffice_to_pdf(stored_filename)

    if src_ext == "svg":
        return _convert_svg(stored_filename, tgt)
    if src_ext in _IMAGE_EXTS:
        return _convert_image(stored_filename, tgt)

    if src_ext in _AUDIO_EXTS:
        return _convert_audio(stored_filename, tgt)

    if src_ext in _VIDEO_EXTS:
        return _convert_video(stored_filename, tgt)

    if src_ext == "zip":
        if tgt == "7z":
            return _repack_zip_to_7z(stored_filename, tgt)
        if tgt == "tar.gz":
            return _repack_zip_to_targz(stored_filename, tgt)
    if src_ext == "7z":
        return _repack_7z_to_zip(stored_filename, tgt)
    if src_ext == "gz":
        return _repack_targz_to_zip(stored_filename, tgt)

    logger.warning("No handler for %s -> %s", src_ext, tgt)
    return False, ""