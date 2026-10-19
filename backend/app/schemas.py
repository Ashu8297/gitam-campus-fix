from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    role: str = Field(pattern="^(student|admin|staff)$")
    identifier: str = Field(min_length=1, max_length=255)  # email or staff ID
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    must_change_password: bool = False
    profile_photo_url: str | None = None
    completion: int = 0


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
