import hmac
import os
import uuid
from pathlib import Path

import httpx
import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from video_provider import CloudflareStream

DATABASE_URL = os.environ["DATABASE_URL"]
WEBHOOK_TOKEN = os.getenv("STREAM_WEBHOOK_TOKEN", "")
router = APIRouter()
provider = CloudflareStream()
web_dir = Path(__file__).parent / "web"


class LessonRequest(BaseModel):
    title: str = Field(min_length=1)


@router.get("/play/{video_id}", response_class=HTMLResponse)
def player_page(video_id: str) -> HTMLResponse:
    template = (web_dir / "player.html").read_text()
    return HTMLResponse(template.replace("{{VIDEO_ID}}", video_id))


@router.get("/upload", response_class=HTMLResponse)
def upload_page() -> HTMLResponse:
    return HTMLResponse((web_dir / "upload.html").read_text())


@router.post("/v1/videos", status_code=201)
def create_lesson(request: LessonRequest) -> dict:
    video_id = uuid.uuid4()
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO videos (id, title, source_url, transcript, provider, upload_status) VALUES (%s, %s, NULL, NULL, 'cloudflare', 'pending')",
            (video_id, request.title),
        )
    return {"video_id": str(video_id), "status": "pending"}


@router.post("/v1/videos/{video_id}/upload-url")
def upload_url(video_id: str) -> dict:
    if not provider.configured:
        raise HTTPException(status_code=503, detail="Cloudflare Stream is not configured")
    try:
        ticket = provider.create_upload()
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE videos SET provider = 'cloudflare', provider_video_id = %s, upload_status = 'uploading', updated_at = now() WHERE id = %s",
            (ticket["uid"], video_id),
        )
    return {"upload_url": ticket["uploadURL"], "uid": ticket["uid"]}


@router.post("/v1/webhooks/stream")
async def stream_webhook(request: Request, token: str = Query(default="")) -> dict:
    if not WEBHOOK_TOKEN or not hmac.compare_digest(token, WEBHOOK_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    payload = await request.json()
    uid = payload.get("uid")
    if not uid:
        raise HTTPException(status_code=400, detail="Missing uid")
    status = payload.get("status")
    upload_status = "playable" if status in {"ready", "ready_to_stream"} else status or "pending"
    result = payload.get("result") or {}
    playback_url = provider.playback_url(uid) if upload_status == "playable" else None
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE videos SET upload_status = %s, playback_url = COALESCE(%s, playback_url), duration_secs = COALESCE(%s, duration_secs), updated_at = now() WHERE provider_video_id = %s",
            (upload_status, playback_url, result.get("duration"), uid),
        )
    return {"ok": True}


@router.get("/v1/videos/{video_id}/player-info")
def player_info(video_id: str) -> dict:
    with psycopg.connect(DATABASE_URL, row_factory=psycopg.rows.dict_row) as connection:
        row = connection.execute(
            "SELECT id, title, provider_video_id, playback_url, thumbnail_url, duration_secs, upload_status FROM videos WHERE id = %s",
            (video_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    return row