from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from schemas.auth import Token, UserCreate, UserResponse
from services.auth_service import (
    authenticate_user,
    create_access_token,
    decode_token,
    get_current_user,
    register_user,
    revoke_token,
)

router = APIRouter()


@router.post("/signup", response_model=UserResponse, status_code=201, summary="Register a new user")
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    """Create a new user account. Returns the created user (without password)."""
    user = register_user(db, payload)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=Token, summary="Login and obtain JWT token")
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """
    Authenticates user credentials (email as username field) with brute-force rate limiting
    and returns a JWT bearer token.
    """
    client_ip = request.client.host if request.client else "unknown"
    user = authenticate_user(
        db,
        email=form_data.username,
        password=form_data.password,
        client_ip=client_ip,
    )
    token = create_access_token(data={"sub": str(user.id)})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=3600,
    )
    return Token(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserResponse, summary="Get current authenticated user")
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Returns the profile of the currently authenticated user."""
    return UserResponse.model_validate(current_user)


@router.get("/users/{user_id}", response_model=UserResponse, summary="Get user profile by ID (own profile only)")
def get_user_by_id(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    Returns a user's profile by ID. Enforces strict per-user authorization:
    users may only access their own profile (prevents horizontal privilege escalation / IDOR).
    """
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not authorized to access another user's profile.",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return UserResponse.model_validate(user)


@router.post("/logout", summary="Logout user, revoke JWT in denylist store, and clear auth cookies")
def logout(
    response: Response,
    authorization: Optional[str] = Header(None),
    access_token_cookie: Optional[str] = Cookie(None, alias="access_token"),
    db: Session = Depends(get_db),
):
    """
    Revokes the active JWT in the persistent token denylist store and clears auth cookies.
    """
    raw_token: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization.split(" ", 1)[1].strip()
    elif access_token_cookie:
        raw_token = access_token_cookie.strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify token is valid before revoking it
    decode_token(raw_token, db=db)
    revoke_token(raw_token, db=db)

    response.delete_cookie("access_token", httponly=True, samesite="lax")
    return {"message": "Successfully logged out and token revoked"}
