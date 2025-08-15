# backend/models.py

from sqlalchemy import create_engine, Column, ForeignKey, Integer, String, Text, Boolean, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# --- Database Setup ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./coldnet.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False, "timeout": 300}
)
# WICHTIG: SessionLocal wird jetzt auch in main.py verwendet
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- ORM Models ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    real_name = Column(String, nullable=True)
    birth_date = Column(Date, nullable=True)
    profile_picture = Column(Text, nullable=True)
    
    chats = relationship("Chat", back_populates="owner")

class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    is_pinned = Column(Boolean, default=False, nullable=False)
    ai_chat_id = Column(Integer, index=True, nullable=False)
    
    owner = relationship("User", back_populates="chats")
    messages = relationship(
        "Message", 
        back_populates="chat", 
        cascade="all, delete-orphan",
        order_by="Message.id"
    )

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)
    sender = Column(String)
    image_data = Column(Text, nullable=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    chat = relationship("Chat", back_populates="messages")
