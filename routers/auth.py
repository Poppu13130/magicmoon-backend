from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
try:  # Compatibility between supabase-py versions
    from supabase._utils import AuthApiError  # type: ignore[attr-defined]
except ImportError:
    try:
        from gotrue.errors import AuthApiError  # type: ignore
    except ImportError:
        AuthApiError = Exception  # type: ignore[misc,assignment]

from core.supabase_client import get_supabase_client

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
async def login(payload: LoginRequest):
    supabase = get_supabase_client()

    try:
        response = supabase.auth.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
    except AuthApiError as exc:  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=getattr(exc, "message", "Supabase authentication failed"),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to contact Supabase authentication service",
        ) from exc

    session = getattr(response, "session", None)
    user = getattr(response, "user", None)
    if session is None or session.access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase did not return a valid session",
        )

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "expires_in": session.expires_in,
        "user": user.model_dump() if hasattr(user, "model_dump") else getattr(user, "__dict__", None),
    }
