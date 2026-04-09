from fastapi import APIRouter, HTTPException, Header
from app.core.supabase import supabase

router = APIRouter(prefix="/auth", tags=["auth"])


def verify_jwt(authorization: str = Header(...)) -> dict:
    """
    Validate a Supabase JWT passed in the Authorization header.
    Returns the decoded user payload or raises 401.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        user_response = supabase.auth.get_user(token)
        if user_response.user is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return {"user_id": user_response.user.id, "email": user_response.user.email}
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.get("/me")
async def get_current_user(user: dict = None):
    """
    Return the authenticated user's basic info.
    Depends on verify_jwt via route-level dependency injection when wired up.
    """
    # Wired up in main.py via dependencies=[Depends(verify_jwt)]
    return user
