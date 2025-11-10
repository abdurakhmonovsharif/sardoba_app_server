from __future__ import annotations

from pathlib import Path

from app.core.config import BASE_DIR


MEDIA_ROOT = BASE_DIR / "media"
PROFILE_PHOTO_DIR = MEDIA_ROOT / "profile_photos"
PROFILE_PHOTO_DIR.mkdir(parents=True, exist_ok=True)


def ensure_media_dirs() -> None:
    PROFILE_PHOTO_DIR.mkdir(parents=True, exist_ok=True)


def profile_photo_path(file_name: str) -> Path:
    safe_name = Path(file_name).name
    return PROFILE_PHOTO_DIR / safe_name


def extract_profile_photo_name(url: str | None) -> str | None:
    if not url:
        return None
    marker = "/files/profile-photo/"
    if marker in url:
        return url.split(marker, 1)[1]
    return Path(url).name
