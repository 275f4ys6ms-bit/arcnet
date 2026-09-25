import json
import os
import uuid
from datetime import date

import psycopg
import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

import video_routes

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
FREE_LIMIT = int(os.getenv("FREE_QUESTIONS_PER_DAY", "5"))
app = FastAPI(title="ArcNet Tutor API", version="1.0.0")
app.include_router(video_routes.router)
queue = redis.from_url(REDIS_URL, decode_responses=True)


class VideoRequest(BaseModel):
    title: str = Field(min_length=1)
    source_url: str | None = None
    transcript: str | None = None


class QuestionRequest(BaseModel):
    learner_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


def search_cards(video_id: str, question: str) -> list[dict]:
    with psycopg.connect(DATABASE_URL, row_factory=psycopg.rows.dict_row) as connection:
        rows = connection.execute(
            "SELECT id, start_seconds, end_seconds, content FROM lesson_cards WHERE video_id = %s ORDER BY start_seconds",
            (video_id,),
        ).fetchall()
    terms = {term.lower() for term in question.split() if len(term) > 2}
    return sorted(rows, key=lambda row: sum(term in row["content"].lower() for term in terms), reverse=True)[:4]


def answer_text(question: str, cards: list[dict]) -> tuple[str, int, int, float]:
    context = "\n".join(f"[{card['start_seconds']:.0f}s] {card['content']}" for card in cards)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Based on the lesson: " + (cards[0]["content"] if cards else "I could not find that in this lesson."), 0, 0, 0
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        temperature=0.2,
        messages=[
            {"role": "system", "content": "Answer only from the supplied lesson context. Be concise and say when the lesson does not contain the answer."},
            {"role": "user", "content": f"Lesson context:\n{context}\n\nQuestion: {question}"},
        ],
    )
    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000
    return response.choices[0].message.content or "I could not formulate an answer.", input_tokens, output_tokens, cost


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/videos", status_code=202)
def register_video(request: VideoRequest) -> dict:
    video_id = uuid.uuid4()
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO videos (id, title, source_url, transcript) VALUES (%s, %s, %s, %s)",
            (video_id, request.title, request.source_url, request.transcript),
        )
    if request.transcript:
        queue.lpush("arcnet:ingest", json.dumps({"video_id": str(video_id), "transcript": request.transcript}))
    return {"video_id": str(video_id), "status": "queued"}


@app.post("/videos/{video_id}/questions")
def ask(video_id: str, request: QuestionRequest):
    with psycopg.connect(DATABASE_URL, row_factory=psycopg.rows.dict_row) as connection:
        existing = connection.execute(
            "SELECT answer, citations FROM questions WHERE learner_id = %s AND video_id = %s AND idempotency_key = %s",
            (request.learner_id, video_id, request.idempotency_key),
        ).fetchone()
        if existing and existing["answer"]:
            return {"answer": existing["answer"], "citations": existing["citations"], "replayed": True}
        count = connection.execute(
            "SELECT count(*) FROM questions WHERE learner_id = %s AND video_id = %s AND created_at::date = %s",
            (request.learner_id, video_id, date.today()),
        ).fetchone()[0]
        if count >= FREE_LIMIT:
            raise HTTPException(status_code=429, detail="Daily free question limit reached")
        connection.execute(
            "INSERT INTO questions (learner_id, video_id, question, idempotency_key) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (request.learner_id, video_id, request.question, request.idempotency_key),
        )
    cards = search_cards(video_id, request.question)
    answer, input_tokens, output_tokens, cost = answer_text(request.question, cards)
    citations = [{"start_seconds": float(card["start_seconds"]), "end_seconds": float(card["end_seconds"])} for card in cards]
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE questions SET answer = %s, citations = %s, input_tokens = %s, output_tokens = %s, cost_usd = %s, status = 'complete', completed_at = now() WHERE learner_id = %s AND video_id = %s AND idempotency_key = %s",
            (answer, json.dumps(citations), input_tokens, output_tokens, cost, request.learner_id, video_id, request.idempotency_key),
        )

    def stream():
        for word in answer.split():
            yield f"data: {json.dumps({'text': word + ' '})}\n\n"
        yield f"data: {json.dumps({'citations': citations, 'done': True})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
