import os
import httpx
import tempfile
import subprocess
from typing import List, Optional, AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status, File, UploadFile, Response, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Annahme, dass diese Module in deinem Projekt existieren
from .models import Base, engine
from . import auth, crud, models, schemas


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Anwendung startet... Erstelle Datenbanktabellen.")
    Base.metadata.create_all(bind=engine)
    yield
    print("Anwendung wird heruntergefahren.")


app = FastAPI(lifespan=lifespan)
AI_SERVER_URL = "http://127.0.0.1:8000" 

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(PROJECT_ROOT, "index.html")


@app.get("/", response_class=FileResponse, include_in_schema=False)
async def serve_frontend():
    if not os.path.exists(INDEX_PATH):
        raise HTTPException(status_code=404, detail="index.html not found.")
    return FileResponse(INDEX_PATH)


class PromptPayload(BaseModel):
    final_prompt: str
    user_text: str
    image_base64: Optional[str] = None


class TTSPayload(BaseModel):
    text: str


# --- HELPER FUNCTION FOR AUDIO NORMALIZATION ---
def ffmpeg_normalize_to_wav(src_path: str, dst_path: str):
    cmd = [ "ffmpeg", "-y", "-i", src_path, "-af", "dynaudnorm=f=150:g=15,volume=3dB", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", dst_path ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --- STT ENDPOINT ---
@app.post("/api/stt/transcribe", tags=["AI & Chat"])
async def proxy_stt(
        file: UploadFile = File(...),
        current_user: models.User = Depends(auth.get_current_user)
):
    src_path = None
    dst_path = None
    try:
        suffix = os.path.splitext(file.filename or ".tmp")[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as src_tmp:
            src_bytes = await file.read()
            src_tmp.write(src_bytes)
            src_path = src_tmp.name
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Upload konnte nicht gespeichert werden: {e}")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as dst_tmp:
            dst_path = dst_tmp.name
        try:
            ffmpeg_normalize_to_wav(src_path, dst_path)
        except subprocess.CalledProcessError:
            simple_cmd = [ "ffmpeg", "-y", "-i", src_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", dst_path ]
            subprocess.run(simple_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        if src_path and os.path.exists(src_path): os.remove(src_path)
        raise HTTPException(status_code=500, detail=f"Audio-Vorverarbeitung fehlgeschlagen: {e}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(dst_path, "rb") as f:
                files = {'file': ('audio.wav', f, 'audio/wav')}
                response = await client.post(f"{AI_SERVER_URL}/stt/transcribe", files=files)
                response.raise_for_status()
                return response.json()
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"AI-Dienst für STT nicht erreichbar: {exc}")
    finally:
        if src_path and os.path.exists(src_path): os.remove(src_path)
        if dst_path and os.path.exists(dst_path): os.remove(dst_path)


@app.post("/api/tts/synthesize", tags=["AI & Chat"])
async def proxy_tts(
        payload: TTSPayload,
        current_user: models.User = Depends(auth.get_current_user)
):
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{AI_SERVER_URL}/tts/synthesize", json={"text": payload.text})
            response.raise_for_status()
            return StreamingResponse(response.iter_bytes(), media_type=response.headers.get("content-type"))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"AI service for TTS is unavailable: {exc}")


@app.post("/api/describe-image/", tags=["AI & Chat"])
async def describe_image(image_file: UploadFile = File(...),
                         current_user: models.User = Depends(auth.get_current_user)):
    try:
        files = {'file': (image_file.filename, await image_file.read(), image_file.content_type)}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{AI_SERVER_URL}/describe-image/", files=files)
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {exc}")


@app.post("/api/register", response_model=schemas.User, tags=["Benutzer & Auth"])
def register_user(user: schemas.UserCreate, db: Session = Depends(auth.get_db)):
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    return crud.create_user(db=db, user=user)


@app.post("/api/token", response_model=schemas.Token, tags=["Benutzer & Auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(auth.get_db)):
    user = crud.get_user_by_username(db, username=form_data.username)
    if not user or not crud.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/profile", response_model=schemas.Profile, tags=["Benutzer & Auth"])
async def read_user_profile(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@app.put("/api/profile", response_model=schemas.Profile, tags=["Benutzer & Auth"])
async def update_profile(profile_data: schemas.ProfileUpdate,
                         current_user: models.User = Depends(auth.get_current_user),
                         db: Session = Depends(auth.get_db)):
    return crud.update_user_profile(db=db, user=current_user, profile_data=profile_data)


@app.put("/api/profile/password", status_code=status.HTTP_204_NO_CONTENT, tags=["Benutzer & Auth"])
async def update_password(password_data: schemas.PasswordUpdate,
                          current_user: models.User = Depends(auth.get_current_user),
                          db: Session = Depends(auth.get_db)):
    if not crud.verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    crud.update_user_password(db=db, user=current_user, new_password=password_data.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/chats", response_model=List[schemas.ChatInfo], tags=["AI & Chat"])
async def read_chats(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    return crud.get_chats_by_owner(db, owner_id=current_user.id)


@app.post("/api/chats", response_model=schemas.ChatInfo, status_code=status.HTTP_201_CREATED, tags=["AI & Chat"])
async def create_new_chat(current_user: models.User = Depends(auth.get_current_user),
                          db: Session = Depends(auth.get_db)):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{AI_SERVER_URL}/chats/")
            response.raise_for_status()
            ai_chat_data = response.json()
            ai_chat_id = ai_chat_data.get("id")
            if not ai_chat_id:
                raise HTTPException(status_code=500, detail="AI server did not return a valid chat ID.")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Could not connect to AI service")
    new_chat = crud.create_chat_for_user(db, title=f"AI Chat #{ai_chat_id}", owner_id=current_user.id,
                                         ai_chat_id=ai_chat_id)
    return new_chat


@app.get("/api/chats/{chat_id}", response_model=schemas.Chat, tags=["AI & Chat"])
async def read_chat_messages(chat_id: int, current_user: models.User = Depends(auth.get_current_user),
                             db: Session = Depends(auth.get_db)):
    chat = crud.get_chat_by_id(db, chat_id=chat_id, owner_id=current_user.id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@app.post("/api/chats/{chat_id}/messages", response_model=schemas.Message, tags=["AI & Chat"])
async def create_chat_message(chat_id: int, payload: PromptPayload,
                              current_user: models.User = Depends(auth.get_current_user),
                              db: Session = Depends(auth.get_db)):
    chat = crud.get_chat_by_id(db, chat_id=chat_id, owner_id=current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    ai_chat_id = chat.ai_chat_id
    ai_payload = {"role": "user", "content": payload.final_prompt, "image_base64": payload.image_base64}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{AI_SERVER_URL}/chats/{ai_chat_id}/messages/", json=ai_payload)
            response.raise_for_status()
            bot_response_data = response.json()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="AI service unavailable")

    user_message = schemas.MessageCreate(content=payload.user_text, sender="user", image_data=payload.image_base64)
    crud.create_message(db, message=user_message, chat_id=chat_id)

    bot_message_content = bot_response_data.get("content", "No response.")
    bot_message = schemas.MessageCreate(content=bot_message_content, sender="coldBot")
    db_bot_message = crud.create_message(db, message=bot_message, chat_id=chat_id)

    return db_bot_message


@app.put("/api/chats/{chat_id}", response_model=schemas.ChatInfo, tags=["AI & Chat"])
def update_chat_details(chat_id: int, update_data: schemas.ChatUpdate,
                        current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(auth.get_db)):
    chat = crud.get_chat_by_id(db, chat_id=chat_id, owner_id=current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if update_data.is_pinned is not None and update_data.is_pinned:
        all_chats = crud.get_chats_by_owner(db, owner_id=current_user.id)
        pinned_count = sum(1 for c in all_chats if c.is_pinned)
        if pinned_count >= 5 and not chat.is_pinned:
            raise HTTPException(status_code=400, detail="Maximum of 5 pinned chats reached.")

    return crud.update_chat(db=db, chat=chat, update_data=update_data)


@app.delete("/api/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["AI & Chat"])
def delete_chat(chat_id: int, current_user: models.User = Depends(auth.get_current_user),
                db: Session = Depends(auth.get_db)):
    chat = crud.get_chat_by_id(db, chat_id=chat_id, owner_id=current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    crud.delete_chat(db=db, chat=chat)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/chats/{chat_id}/messages/stream-audio", tags=["AI & Chat"])
async def proxy_stream_audio(
    chat_id: int,
    request: Request,
    current_user: models.User = Depends(auth.get_current_user)
):
    chat = crud.get_chat_by_id(db=next(auth.get_db()), chat_id=chat_id, owner_id=current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    ai_chat_id = chat.ai_chat_id
    ai_server_url = f"{AI_SERVER_URL}/chats/{ai_chat_id}/messages/stream-audio"
    payload = await request.json()

    async def stream_generator() -> AsyncGenerator[bytes, None]:
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", ai_server_url, json=payload, timeout=None) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except httpx.RequestError as e:
            print(f"Proxy-Fehler beim Streamen zum AI-Server: {e}")
            pass

    return StreamingResponse(stream_generator(), media_type="application/octet-stream")

# --- NEUER SYNC ENDPUNKT ---
@app.post("/api/chats/{chat_id}/sync", status_code=status.HTTP_204_NO_CONTENT, tags=["AI & Chat"])
async def sync_chat_history(
    chat_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(auth.get_db)
):
    chat = crud.get_chat_by_id(db, chat_id=chat_id, owner_id=current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    ai_chat_id = chat.ai_chat_id
    ai_server_url = f"{AI_SERVER_URL}/chats/{ai_chat_id}/messages/"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(ai_server_url)
            response.raise_for_status()
            ai_messages = response.json()

        db.query(models.Message).filter(models.Message.chat_id == chat_id).delete(synchronize_session=False)

        for msg in ai_messages:
            sender = "user" if msg.get("role") == "user" else "coldBot"
            message_to_create = schemas.MessageCreate(
                sender=sender,
                content=msg.get("content"),
                image_data=msg.get("image_base64") # Annahme, dass der AI-Server dies bereitstellt
            )
            crud.create_message(db, message=message_to_create, chat_id=chat_id)
        
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except httpx.RequestError as e:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"Could not connect to AI service for sync: {e}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An error occurred during sync: {e}")
