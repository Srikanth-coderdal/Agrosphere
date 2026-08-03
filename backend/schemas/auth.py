from pydantic import BaseModel, Field, EmailStr


class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, description="User's full name.")
    email: EmailStr = Field(..., description="User's email address (must be unique).")
    password: str = Field(..., min_length=8, description="Plain-text password (min 8 characters).")


class UserLogin(BaseModel):
    email: EmailStr = Field(..., description="Registered email address.")
    password: str = Field(..., description="Plain-text password.")


class Token(BaseModel):
    access_token: str = Field(..., description="JWT bearer token.")
    token_type: str = Field(default="bearer", description="Token type.")


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    is_active: bool

    model_config = {"from_attributes": True}
