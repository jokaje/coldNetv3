# backend/schemas.py

from pydantic import BaseModel
from typing import List, Optional
from datetime import date

class MessageBase(BaseModel):
    content: str
    sender: str
    image_data: Optional[str] = None

class MessageCreate(MessageBase):
    pass

class Message(MessageBase):
    id: int
    chat_id: int
    class Config:
        from_attributes = True

class ChatBase(BaseModel):
    title: str

class ChatCreate(ChatBase):
    pass

class ChatUpdate(BaseModel):
    title: Optional[str] = None
    is_pinned: Optional[bool] = None

class Chat(ChatBase):
    id: int
    owner_id: int
    is_pinned: bool
    ai_chat_id: int
    messages: List[Message] = []
    class Config:
        from_attributes = True

class ChatInfo(BaseModel):
    id: int
    title: str
    is_pinned: bool
    ai_chat_id: int
    class Config:
        from_attributes = True

# --- NEUE PROFIL-SCHEMAS ---
class ProfileBase(BaseModel):
    username: str
    real_name: Optional[str] = None
    birth_date: Optional[date] = None
    profile_picture: Optional[str] = None

class Profile(ProfileBase):
    id: int
    class Config:
        from_attributes = True

class ProfileUpdate(BaseModel):
    real_name: Optional[str] = None
    birth_date: Optional[date] = None
    profile_picture: Optional[str] = None

class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str

# --- Angepasste User-Schemas ---
class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class User(Profile): # Erbt jetzt von Profile, um alle Felder zu haben
    chats: List[ChatInfo] = []
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
