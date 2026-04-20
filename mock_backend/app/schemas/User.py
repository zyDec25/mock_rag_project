from pydantic import BaseModel


class RegisterRequest(BaseModel):
  username: str
  password: str


class LoginRequest(BaseModel):
  username: str
  password: str


class UserInfoResponse(BaseModel):
  id: int
  username: str
  
  class Config:
    from_attributes = True

class RegisterResponse(BaseModel):
  message: str
  user: UserInfoResponse
  
class LoginResponse(BaseModel):
  message: str
  access_token: str
  token_type: str = 'bearer'
  user: UserInfoResponse
