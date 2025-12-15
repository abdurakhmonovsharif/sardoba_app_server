from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_client, get_db
from app.core.storage import extract_profile_photo_name, profile_photo_path
from app.models import User
from app.services import UserService

router = APIRouter(prefix="/user", tags=["user"])


@router.delete("/delete", status_code=status.HTTP_200_OK)
def delete_account(
    current_user: User = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    photo_name = extract_profile_photo_name(current_user.profile_photo_url)
    if photo_name:
        path = profile_photo_path(photo_name)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
    return UserService(db).delete_user(current_user)
