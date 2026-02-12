from __future__ import annotations
from pathlib import Path
import shutil
from uuid import uuid4
from typing import Optional


UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE_MB = 50


class FileUploadError(Exception):
    pass


def ensure_upload_directory() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def validate_file_extension(filename: str, allowed_extensions: set = ALLOWED_EXTENSIONS) -> None:
    if not filename:
        raise FileUploadError("filename is required")
    
    file_path = Path(filename)
    if file_path.suffix.lower() not in allowed_extensions:
        raise FileUploadError(f"File type not allowed. Allowed: {', '.join(allowed_extensions)}")


def generate_unique_filename(original_filename: str) -> str:
    if not original_filename:
        raise FileUploadError("original_filename is required")
    
    file_path = Path(original_filename)
    extension = file_path.suffix.lower()
    unique_id = str(uuid4())
    
    return f"{unique_id}{extension}"


def save_uploaded_file(file_content: bytes, original_filename: str) -> str:
    if not file_content:
        raise FileUploadError("file_content cannot be empty")
    
    if not original_filename:
        raise FileUploadError("original_filename is required")
    
    file_size_mb = len(file_content) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise FileUploadError(f"File size ({file_size_mb:.1f}MB) exceeds maximum allowed size ({MAX_FILE_SIZE_MB}MB)")
    
    validate_file_extension(original_filename)
    
    upload_dir = ensure_upload_directory()
    unique_filename = generate_unique_filename(original_filename)
    file_path = upload_dir / unique_filename
    
    try:
        with open(file_path, "wb") as f:
            f.write(file_content)
    except Exception as e:
        raise FileUploadError(f"Failed to save file: {str(e)}")
    
    return str(file_path)


def delete_uploaded_file(file_path: str) -> None:
    if not file_path:
        return
    
    path = Path(file_path)
    if path.exists() and path.is_file():
        try:
            path.unlink()
        except Exception:
            pass
