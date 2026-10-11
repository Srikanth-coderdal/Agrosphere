"""
Upload security service (Phase 6.2):
- Enforces strict maximum upload size (5 MB)
- Validates real image format via magic bytes / Pillow decode (ignores spoofed extensions/MIME headers)
- Re-encodes images server-side onto a fresh canvas to strip all EXIF/GPS metadata and embedded payloads
- Stores sanitized images ONLY when explicit user consent is given, using generated UUID filenames
- Supports full user-initiated deletion of consented uploads from disk and database
"""
import io
import os
from pathlib import Path
from typing import Optional, Tuple
import uuid

from fastapi import HTTPException, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from models.user import ConsentedUpload

# Limit maximum upload size to 5 MB
MAX_UPLOAD_SIZE_BYTES: int = 5 * 1024 * 1024  # 5,242,880 bytes

# Guard against decompression bombs (max 25 megapixels)
Image.MAX_IMAGE_PIXELS = 25_000_000

ALLOWED_PIL_FORMATS = {"JPEG", "PNG", "WEBP"}

BASE_DIR = Path(__file__).resolve().parent.parent
CONSENTED_UPLOADS_DIR = BASE_DIR / "data" / "consented_uploads"


def validate_and_sanitize_image(raw_bytes: bytes) -> Tuple[bytes, str]:
    """
    1. Enforce non-empty and <= MAX_UPLOAD_SIZE_BYTES.
    2. Decode magic bytes with Pillow (`verify()`) and check format in ALLOWED_PIL_FORMATS.
    3. Re-encode pixels onto a fresh RGB canvas without any EXIF, ICC, or comment metadata.
    Returns (sanitized_jpeg_bytes, "image/jpeg").
    """
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty.",
        )

    if len(raw_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Uploaded image exceeds the maximum allowed size of {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    # Pass 1: Verify magic bytes and structural integrity via Pillow
    try:
        with Image.open(io.BytesIO(raw_bytes)) as probe:
            detected_format = (probe.format or "").upper()
            probe.verify()
    except Image.DecompressionBombError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image dimensions exceed safety limits.",
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or corrupted image file. Magic-byte verification failed.",
        ) from exc

    if detected_format not in ALLOWED_PIL_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported real image format '{detected_format or 'unknown'}'. Allowed formats: JPEG, PNG, WEBP.",
        )

    # Pass 2: Full pixel decode and clean re-encoding onto a fresh canvas (strips EXIF/GPS & payloads)
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            img.load()
            rgb_source = img.convert("RGB")
            clean_canvas = Image.new("RGB", rgb_source.size)
            clean_canvas.paste(rgb_source)

            out_buf = io.BytesIO()
            clean_canvas.save(out_buf, format="JPEG", quality=85, optimize=True)
            sanitized_bytes = out_buf.getvalue()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to decode and sanitize uploaded image.",
        ) from exc

    return sanitized_bytes, "image/jpeg"


def store_consented_image(
    db: Session,
    user_id: int,
    crop_type: str,
    sanitized_bytes: bytes,
) -> str:
    """
    Persist a sanitized, metadata-stripped image ONLY when explicit user consent is True.
    Uses a random UUID4 filename so user-supplied filenames never touch the filesystem.
    """
    CONSENTED_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex
    generated_filename = f"{upload_id}.jpg"
    target_path = CONSENTED_UPLOADS_DIR / generated_filename

    target_path.write_bytes(sanitized_bytes)

    record = ConsentedUpload(
        upload_id=upload_id,
        user_id=user_id,
        filename=generated_filename,
        crop_type=crop_type,
    )
    db.add(record)
    db.commit()
    return upload_id


def delete_consented_upload_by_id(db: Session, user_id: int, upload_id: str) -> None:
    """Delete a single consented image upload owned by user_id from disk and DB."""
    record: Optional[ConsentedUpload] = (
        db.query(ConsentedUpload).filter(ConsentedUpload.upload_id == upload_id).first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored upload not found.",
        )
    if record.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You can only delete your own stored uploads.",
        )

    file_path = CONSENTED_UPLOADS_DIR / os.path.basename(record.filename)
    if file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            pass

    db.delete(record)
    db.commit()


def delete_all_consented_uploads_for_user(db: Session, user_id: int) -> int:
    """Delete all consented image uploads owned by user_id from disk and DB."""
    records = db.query(ConsentedUpload).filter(ConsentedUpload.user_id == user_id).all()
    count = 0
    for record in records:
        file_path = CONSENTED_UPLOADS_DIR / os.path.basename(record.filename)
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass
        db.delete(record)
        count += 1
    db.commit()
    return count
