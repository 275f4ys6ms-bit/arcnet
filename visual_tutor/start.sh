#!/usr/bin/env bash
set -e
uvicorn token_server:app --host 0.0.0.0 --port "${PORT:-10000}" &
exec python voice_agent.py start
