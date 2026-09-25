# Live AI visual tutor

A no-GPU visual tutoring slice: a streamed lesson emits `[[VISUAL: ...]]` tags, the parser turns them into scene commands, and a browser Canvas renderer receives them over WebSocket. The optional Step 2 voice agent uses LiveKit and the same `visual_schema.expand()` and `/ws-agent` path.

## Step 1

```bash
cd visual_tutor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --port 8000
```

Open `http://localhost:8000`, then trigger the mock lesson:

```bash
curl -X POST "http://localhost:8000/api/lesson?mock=true"
```

Live mode requires `OPENAI_API_KEY`:

```bash
export OPENAI_API_KEY=sk-...
curl -X POST "http://localhost:8000/api/lesson?mock=false&topic=mine+safety+at+heights"
```

Run the full local check with `python test_e2e.py`. It verifies seven tags, split-tag parsing, seven scene commands, clean captions, and the HTTP-to-WebSocket round trip.

## Step 2 voice loop

Create a LiveKit Cloud project, set the variables in `.env`, install `requirements-agent.txt`, and run:

```bash
export CANVAS_WS=ws://localhost:8000/ws-agent
python voice_agent.py dev
uvicorn token_server:app --port 8001
```

The browser can join with `/api/token`; `/livekit` contains a minimal client. The agent's `update_visual_canvas` tool feeds the same schema and scene graph as Step 1.

For deployment, `Dockerfile` serves Step 1. `render.yaml` and `start.sh` describe a token server plus outbound LiveKit agent worker. A laptop demo can be exposed with `cloudflared tunnel --url http://localhost:8000`; HTTPS pages require `wss://`.
