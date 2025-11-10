from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import get_current_client, get_db
from app.core.storage import extract_profile_photo_name, profile_photo_path, PROFILE_PHOTO_DIR
from app.models import User
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")
    PROFILE_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid4().hex}{ext}"
    destination = PROFILE_PHOTO_DIR / file_name
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(file_path)
