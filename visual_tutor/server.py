import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from mock_lesson import MOCK_STREAM
from parser import VisualStreamParser

BASE = Path(__file__).parent
app = FastAPI()
CLIENTS: set[WebSocket] = set()
OBJECTS: dict = {}
ORDER: list = []


async def broadcast(message: dict):
    dead = []
    for websocket in CLIENTS:
        try:
            await websocket.send_json(message)
        except Exception:
            dead.append(websocket)
    for websocket in dead:
        CLIENTS.discard(websocket)


def apply(command: dict):
    operation = command.get("op")
    if operation == "erase":
        if command.get("id") == "*":
            OBJECTS.clear()
            ORDER.clear()
        else:
            OBJECTS.pop(command["id"], None)
            if command["id"] in ORDER:
                ORDER.remove(command["id"])
    elif operation == "draw":
        if command["id"] not in OBJECTS:
            ORDER.append(command["id"])
        OBJECTS[command["id"]] = command
    asyncio.create_task(broadcast({"type": "scene", "cmd": command}))


@app.get("/")
async def index():
    return HTMLResponse((BASE / "client.html").read_text())


@app.get("/livekit")
async def livekit_client():
    return HTMLResponse((BASE / "livekit_client.html").read_text())


@app.websocket("/ws")
async def client_ws(websocket: WebSocket):
    await websocket.accept()
    CLIENTS.add(websocket)
    await websocket.send_json({"type": "snapshot", "objects": [OBJECTS[item] for item in ORDER]})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        CLIENTS.discard(websocket)


@app.websocket("/ws-agent")
async def agent_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            message = json.loads(await websocket.receive_text())
            if message.get("type") == "scene":
                apply(message["cmd"])
    except WebSocketDisconnect:
        pass


@app.post("/api/lesson")
async def start_lesson(mock: bool = True, topic: str = "photosynthesis"):
    asyncio.create_task(run_lesson(mock, topic))
    return {"status": "started", "topic": topic, "mock": mock}


async def run_lesson(mock: bool, topic: str):
    async def on_text(text: str):
        await broadcast({"type": "caption", "text": " ".join(text.split())})

    async def on_visual(command: dict):
        apply(command)

    parser = VisualStreamParser(on_text, on_visual)
    try:
        async for token in token_stream(mock, topic):
            await parser.feed(token)
        await parser.close()
    except Exception as error:
        await broadcast({"type": "caption", "text": f"[lesson error: {error}]"})


async def token_stream(mock: bool, topic: str):
    if mock:
        for chunk, pause_ms in MOCK_STREAM:
            for index in range(0, len(chunk), 4):
                yield chunk[index:index + 4]
                await asyncio.sleep(0.001)
            await asyncio.sleep(pause_ms / 1000)
        return
    from openai import AsyncOpenAI
    client = AsyncOpenAI()
    stream = await client.chat.completions.create(
        model=os.getenv("TUTOR_MODEL", "gpt-4o-mini"), temperature=0.4, stream=True,
        messages=[
            {"role": "system", "content": (BASE / "system_prompt.md").read_text()},
            {"role": "user", "content": f"Explain {topic} step by step, illustrating each step on the live canvas."},
        ],
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
