import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

from mock_lesson import MOCK_STREAM

ROOT = Path(__file__).parent
URL = "http://127.0.0.1:8765"


def mock_tag_count():
    return sum(chunk.count("[[VISUAL:") for chunk, _ in MOCK_STREAM)


async def exercise_server():
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8765"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(URL, timeout=0.2) as response:
                    assert response.status == 200
                    assert b"canvas" in response.read()
                with urllib.request.urlopen(f"{URL}/livekit", timeout=0.2) as response:
                    assert response.status == 200
                    assert b"LiveKit" in response.read()
                    break
            except OSError:
                await asyncio.sleep(0.1)
        else:
            raise AssertionError("uvicorn did not start")

        async with websockets.connect(f"ws://127.0.0.1:8765/ws") as socket:
            snapshot = json.loads(await socket.recv())
            assert snapshot == {"type": "snapshot", "objects": []}
            request = urllib.request.Request(
                f"{URL}/api/lesson?mock=true", method="POST"
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                assert json.load(response)["status"] == "started"

            scenes, captions = [], []
            deadline = time.monotonic() + 12
            while (len(scenes) < 7 or not any("To recap:" in caption for caption in captions)) and time.monotonic() < deadline:
                message = json.loads(await asyncio.wait_for(socket.recv(), 2))
                if message["type"] == "scene":
                    scenes.append(message["cmd"])
                elif message["type"] == "caption":
                    captions.append(message["text"])

            assert len(scenes) == 7, scenes
            assert scenes[-1] == {"op": "erase", "id": "*"}
            assert any("To recap:" in caption for caption in captions)
            assert all("[[VISUAL:" not in caption for caption in captions)

    finally:
        process.terminate()
        process.wait(timeout=5)


async def main():
    assert mock_tag_count() == 7
    await exercise_server()
    print("mock tags: 7")
    print("scene commands: 7")
    print("WebSocket round-trip: PASS")


if __name__ == "__main__":
    asyncio.run(main())
