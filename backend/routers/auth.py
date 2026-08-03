from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from schemas.auth import Token, UserCreate, UserResponse
from services.auth_service import (
    authenticate_user,
    create_access_token,
    get_current_user,
    register_user,
)

router = APIRouter()


@router.post("/signup", response_model=UserResponse, status_code=201, summary="Register a new user")
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    """Create a new user account. Returns the created user (without password)."""
    user = register_user(db, payload)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=Token, summary="Login and obtain JWT token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """
    Authenticates user credentials (email as username field) and returns a JWT bearer token.
    Compatible with OAuth2 password flow for Swagger UI.
    """
    user = authenticate_user(db, email=form_data.username, password=form_data.password)
    token = create_access_token(data={"sub": str(user.id)})
    return Token(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserResponse, summary="Get current authenticated user")
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Returns the profile of the currently authenticated user."""
    return UserResponse.model_validate(current_user)
