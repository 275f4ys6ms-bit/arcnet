import json
import logging
import os
import re
import time

import psycopg
import redis
from openai import OpenAI
from pgvector.psycopg import register_vector

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
QUEUE_NAME = "arcnet:ingest"


def parse_srt(text: str) -> list[dict]:
    cards = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start, end = lines[1].split(" --> ", 1)
        cards.append({
            "start_seconds": timestamp_seconds(start),
            "end_seconds": timestamp_seconds(end),
            "content": " ".join(line.strip() for line in lines[2:]),
        })
    return cards


def timestamp_seconds(value: str) -> float:
    hours, minutes, rest = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def embeddings(contents: list[str]) -> list[list[float] | None]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return [None] * len(contents)
    client = OpenAI(api_key=api_key)
    response = client.embeddings.create(
        model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        input=contents,
    )
    return [item.embedding for item in response.data]


def process_job(job: dict) -> None:
    video_id = job["video_id"]
    cards = parse_srt(job["transcript"])
    vectors = embeddings([card["content"] for card in cards])
    with psycopg.connect(DATABASE_URL) as connection:
        register_vector(connection)
        with connection.cursor() as cursor:
            cursor.execute("UPDATE videos SET status = 'processing', updated_at = now() WHERE id = %s", (video_id,))
            cursor.execute("DELETE FROM lesson_cards WHERE video_id = %s", (video_id,))
            for card, vector in zip(cards, vectors):
                cursor.execute(
                    "INSERT INTO lesson_cards (video_id, start_seconds, end_seconds, content, embedding) VALUES (%s, %s, %s, %s, %s)",
                    (video_id, card["start_seconds"], card["end_seconds"], card["content"], vector),
                )
            cursor.execute("UPDATE videos SET status = 'ready', updated_at = now() WHERE id = %s", (video_id,))
    LOGGER.info("Ingested %s cards for video %s", len(cards), video_id)


def main() -> None:
    queue = redis.from_url(REDIS_URL, decode_responses=True)
    LOGGER.info("Waiting for ingestion jobs")
    while True:
        _, payload = queue.brpop(QUEUE_NAME)
        job = json.loads(payload)
        try:
            process_job(job)
        except Exception:
            LOGGER.exception("Ingestion failed for video %s", job.get("video_id"))
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute("UPDATE videos SET status = 'failed', updated_at = now() WHERE id = %s", (job["video_id"],))
        time.sleep(0.1)


if __name__ == "__main__":
    main()
