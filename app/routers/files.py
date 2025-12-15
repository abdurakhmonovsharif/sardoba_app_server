from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import get_current_client, get_current_manager, get_db
from app.core.localization import localize_message
from app.core.storage import NEWS_IMAGE_DIR, PROFILE_PHOTO_DIR, extract_profile_photo_name, news_image_path, profile_photo_path
from app.models import Staff, User
from app.schemas import UserRead

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/profile-photo", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def upload_profile_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> UserRead:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message("Missing filename"))
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message("Unsupported file type"))
    PROFILE_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid4().hex}{ext}"
    destination = PROFILE_PHOTO_DIR / file_name
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message("Empty file"))
    with destination.open("wb") as buffer:
        buffer.write(contents)

    old_name = extract_profile_photo_name(current_user.profile_photo_url)
    if old_name and old_name != file_name:
        old_path = profile_photo_path(old_name)
        if old_path.exists():
            try:
                old_path.unlink()
            except OSError:
                pass

    settings = get_settings()
    relative_path = f"{settings.API_V1_PREFIX}/files/profile-photo/{file_name}"
    current_user.profile_photo_url = relative_path
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return UserRead.from_orm(current_user)


@router.get("/profile-photo/{file_name}")
def get_profile_photo(file_name: str):
    safe_name = Path(file_name).name
    file_path = profile_photo_path(safe_name)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message("File not found"))
    return FileResponse(file_path)


@router.delete("/profile-photo", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile_photo(
    current_user: User = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> None:
    photo_name = extract_profile_photo_name(current_user.profile_photo_url)
    if photo_name:
        path = profile_photo_path(photo_name)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
    if current_user.profile_photo_url:
        current_user.profile_photo_url = None
        db.add(current_user)
        db.commit()


async def _ensure_news_upload_file(
    request: Request,
) -> UploadFile:
    form = await request.form()
    for key in ("file", "image", "news_image"):
        candidate = form.get(key)
        if isinstance(candidate, UploadFile):
            return candidate
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message("Missing filename"))


async def _store_news_image(upload_file: UploadFile, manager: Staff) -> dict[str, str]:
    ext = Path(upload_file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message("Unsupported file type"))
    NEWS_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid4().hex}-{manager.id}{ext}"
    destination = NEWS_IMAGE_DIR / file_name
    contents = await upload_file.read()
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message("Empty file"))
    with destination.open("wb") as buffer:
        buffer.write(contents)
    settings = get_settings()
    relative_path = f"{settings.API_V1_PREFIX}/files/news_images/{file_name}"
    return {"image_url": relative_path}


@router.post("/news_images", status_code=status.HTTP_201_CREATED)
async def upload_news_image(
    upload_file: UploadFile = Depends(_ensure_news_upload_file),
    manager: Staff = Depends(get_current_manager),
) -> dict[str, str]:
    return await _store_news_image(upload_file, manager)


@router.post("/news-image", include_in_schema=False)
async def upload_news_image_legacy(
    request: Request,
    manager: Staff = Depends(get_current_manager),
) -> dict[str, str]:
    upload_file = await _ensure_news_upload_file(request)
    return await _store_news_image(upload_file, manager)


@router.get("/news_images/{file_name}")
def get_news_image(file_name: str):
    safe_name = Path(file_name).name
    file_path = news_image_path(safe_name)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message("File not found"))
    return FileResponse(file_path)


@router.get("/news-image/{file_name}", include_in_schema=False)
def get_news_image_legacy(file_name: str):
    return get_news_image(file_name)


@router.delete("/news_images/{file_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_news_image(
    file_name: str,
    manager: Staff = Depends(get_current_manager),
) -> None:
    safe_name = Path(file_name).name
    file_path = news_image_path(safe_name)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=localize_message("File not found"))
    try:
        file_path.unlink()
    except OSError:
        pass
