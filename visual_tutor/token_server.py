import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from livekit import api

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/config")
async def config():
    return {"livekit_url": os.getenv("LIVEKIT_URL", "")}


@app.get("/api/token")
async def token(room: str = "tutor-demo", name: str = "learner"):
    access_token = (api.AccessToken().with_identity(name).with_name(name).with_grants(
        api.VideoGrants(room_join=True, room=room)
    ))
    return {"token": access_token.to_jwt(), "url": os.getenv("LIVEKIT_URL", "")}
