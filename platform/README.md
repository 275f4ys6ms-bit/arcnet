# ArcNet Phase 2

This directory contains persistent lesson memory, a Redis-backed ingestion queue, an ingestion worker, a tutor API, and the Cloudflare Stream upload/player flow.

## Run it

```bash
cp .env.example .env
# Set OPENAI_API_KEY in .env for generated answers and vector embeddings.
docker compose up --build
```

For Cloudflare Stream uploads, set `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`,
`CLOUDFLARE_CUSTOMER_CODE`, and `STREAM_WEBHOOK_TOKEN` in `.env`. The upload-ticket
check skips cleanly when the Cloudflare settings are empty.

Run the Phase 2 smoke test from this directory while the services are running:

```bash
bash test_phase2.sh
```

The player is available at `http://localhost:8000/play/VIDEO_ID` and the upload form
at `http://localhost:8000/upload`.

Open `http://localhost:8000/docs` for the interactive API.

Register a lesson:

```bash
curl -X POST http://localhost:8000/videos \
  -H 'content-type: application/json' \
  --data "$(python -c 'import json; print(json.dumps({"title":"How to cook rice","source_url":"sample.srt","transcript":open("sample.srt").read()}))')"
```

The response contains a `video_id`. After the worker marks the video ready, ask a question:

```bash
curl -N -X POST http://localhost:8000/videos/VIDEO_ID/questions \
  -H 'content-type: application/json' \
  -d '{"learner_id":"demo-learner","question":"Why should I rinse the rice?","idempotency_key":"demo-1"}'
```

The response is server-sent events containing answer text and timestamp citations. Reusing the same idempotency key returns the stored answer without calling the model again. The default free allowance is five questions per learner, per video, per UTC day.

## Services

- **Postgres + pgvector** stores videos, timestamped lesson cards, questions, costs, and wallets.
- **Redis** holds ingestion jobs and is ready for session/rate-limit state.
- **Ingestor** parses SRT transcripts into cards and creates embeddings when an OpenAI key is configured.
- **Tutor** performs retrieval, enforces the daily limit, records Q&A, and streams the answer.

Authentication, paid packs, creator payouts, and video CDN integration are intentionally left for later phases. Before production, add authentication, transactional rate-limit reservation, model usage accounting, and a real upload/transcription pipeline.
