import logging
from datetime import datetime
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
from app.schemas import UserRead, FileListResponse, FileRead, Pagination

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

router = APIRouter(prefix="/files", tags=["files"])
logger = logging.getLogger(__name__)


@router.get("", response_model=FileListResponse)
def list_files(
    page: int = Depends(lambda page: int(page) if page else 1),
    page_size: int = Depends(lambda page_size: int(page_size) if page_size else 12),
    manager: Staff = Depends(get_current_manager),
) -> FileListResponse:
    all_files: list[FileRead] = []
    settings = get_settings()

    # Profile photos
    if PROFILE_PHOTO_DIR.exists():
        for f in PROFILE_PHOTO_DIR.iterdir():
            if f.is_file() and not f.name.startswith("."):
                stats = f.stat()
                all_files.append(
                    FileRead(
                        name=f.name,
                        url=f"{settings.API_V1_PREFIX}/files/profile-photo/{f.name}",
                        size=stats.st_size,
                        created_at=datetime.fromtimestamp(stats.st_ctime),
                        type="profile_photo",
                    )
                )

    # News images
    if NEWS_IMAGE_DIR.exists():
        for f in NEWS_IMAGE_DIR.iterdir():
            if f.is_file() and not f.name.startswith("."):
                stats = f.stat()
                all_files.append(
                    FileRead(
                        name=f.name,
                        url=f"{settings.API_V1_PREFIX}/files/news_images/{f.name}",
                        size=stats.st_size,
                        created_at=datetime.fromtimestamp(stats.st_ctime),
                        type="news_image",
                    )
                )

    # Sort by creation time desc
    all_files.sort(key=lambda x: x.created_at, reverse=True)

    total = len(all_files)
    start = (page - 1) * page_size
    end = start + page_size
    items = all_files[start:end]

    return FileListResponse(
        pagination=Pagination(page=page, size=page_size, total=total),
        items=items,
    )


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
    file: UploadFile = File(None),
    image: UploadFile = File(None),
    news_image: UploadFile = File(None),
    manager: Staff = Depends(get_current_manager),
) -> dict[str, str]:
    upload_file = file or image or news_image
    if not upload_file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=localize_message("Missing filename"))
    return await _store_news_image(upload_file, manager)


@router.post("/news-images", status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/news-image", status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/news_image", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def upload_news_image_aliases(
    file: UploadFile = File(None),
    image: UploadFile = File(None),
    news_image: UploadFile = File(None),
    manager: Staff = Depends(get_current_manager),
) -> dict[str, str]:
    return await upload_news_image(file, image, news_image, manager)


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
