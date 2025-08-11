# backend/crud.py

from sqlalchemy.orm import Session
from sqlalchemy import desc
from passlib.context import CryptContext
from . import models, schemas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

# --- User CRUD ---
def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = get_password_hash(user.password)
    db_user = models.User(username=user.username, hashed_password=hashed_password)
    db.add(db_user)
    db.flush()
    db.refresh(db_user)
    return db_user

# NEU: Funktion zum Aktualisieren des Profils
def update_user_profile(db: Session, user: models.User, profile_data: schemas.ProfileUpdate):
    user.real_name = profile_data.real_name
    user.birth_date = profile_data.birth_date
    user.profile_picture = profile_data.profile_picture
    db.add(user)
    db.flush()
    db.refresh(user)
    return user

# NEU: Funktion zum Ändern des Passworts
def update_user_password(db: Session, user: models.User, new_password: str):
    user.hashed_password = get_password_hash(new_password)
    db.add(user)
    db.flush()
    db.refresh(user)
    return user

# --- Chat CRUD ---
def get_chats_by_owner(db: Session, owner_id: int):
    return db.query(models.Chat).filter(models.Chat.owner_id == owner_id).order_by(desc(models.Chat.is_pinned), desc(models.Chat.id)).all()

def get_chat_by_id(db: Session, chat_id: int, owner_id: int):
    return db.query(models.Chat).filter(models.Chat.id == chat_id, models.Chat.owner_id == owner_id).first()

def create_chat_for_user(db: Session, title: str, owner_id: int, ai_chat_id: int):
    db_chat = models.Chat(title=title, owner_id=owner_id, ai_chat_id=ai_chat_id)
    db.add(db_chat)
    db.flush()
    db.refresh(db_chat)
    return db_chat

def update_chat(db: Session, chat: models.Chat, update_data: schemas.ChatUpdate):
    if update_data.title is not None:
        chat.title = update_data.title
    if update_data.is_pinned is not None:
        chat.is_pinned = update_data.is_pinned
    db.add(chat)
    db.flush()
    db.refresh(chat)
    return chat

def delete_chat(db: Session, chat: models.Chat):
    db.delete(chat)
    db.flush()

# --- Message CRUD ---
def create_message(db: Session, message: schemas.MessageCreate, chat_id: int):
    db_message = models.Message(**message.dict(), chat_id=chat_id)
    db.add(db_message)
    db.flush()
    db.refresh(db_message)
    return db_message
