# Layered Context Document Analyst

A local reference implementation for the article "Long Context Isn't Memory". The app lets you upload documents, ask questions over a long session, and inspect exactly what was sent to the model on every turn.

## Run

```bash
docker compose up --build
```

Open:

- Frontend: <http://localhost:3000>
- Backend: <http://localhost:8000>

The app works in a local demo mode if API keys are not set. In demo mode the provider adapters return deterministic placeholder completions, which is useful for exploring traces and UI behaviour without spending tokens.

## Environment

```bash
LLM_PROVIDER=openai          # openai | anthropic | mistral
LLM_MODEL=gpt-5-mini
PLANNER_MODEL=gpt-5-mini   # optional; use a cheaper/smaller model for L5 where supported
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
MISTRAL_API_KEY=...
RECENT_TURN_COUNT=6
SUMMARY_THRESHOLD_PAIRS=4
SUMMARY_BATCH_PAIRS=4
MAX_UPLOAD_BYTES=10485760
MAX_MESSAGE_CHARS=12000
```

Switching `LLM_PROVIDER` between `openai`, `anthropic`, and `mistral` changes the adapter without code changes. If `LLM_MODEL` is blank or belongs to another provider, the backend picks a provider-native default: `gpt-5-mini`, `claude-sonnet-4-20250514`, or `mistral-small-2603`. API keys are read from environment variables and are never returned to the frontend.

## The Five Layers

Every layered-mode turn is assembled in this order and returned in the trace:

1. `L1_system`: static system constraints set when the session is created.
2. `L2_documents`: all currently loaded PDF, text, and Markdown documents with names.
3. `L3_summary`: append-only rolling summaries of older evicted conversation pairs.
4. `L4_recent`: the latest verbatim turns in a sliding window, defaulting to 6 messages.
5. `L5_working`: per-turn working state built from a planner call, the latest question, extracted entities, sub-questions, relevant document sections, and document observations.

Naive mode intentionally skips `L3_summary` and `L5_working`, and its `L4_recent` block contains the full verbatim history. This makes prompt growth visible in the Layer Inspector and Metrics panel.

## Summarisation

When turns age out of `L4_recent`, complete user/assistant pairs enter a pending summarisation buffer derived from persisted turns. Once the pending buffer reaches `SUMMARY_THRESHOLD_PAIRS` (default 4), the summariser makes a separate LLM call:

> Compress the following exchange into 2-4 sentences capturing decisions made, facts established, and open threads. Preserve specifics that might be referenced later.

The summary is stored in `summaries`, included in `L3_summary` on the same turn, and exposed as a summariser event in the inspector.

## Persistence

SQLite is mounted at `./data/layered_context.db`. Sessions, documents, turns, summaries, and traces survive browser and container restarts. The frontend stores the current session id in the URL as `?session=...`, so reopening that URL restores the same state.

## Tests

```bash
uv run pytest
```

The test suite covers layer assembly ordering, token-total accounting, sliding-window eviction, summariser triggering, and the provider adapter contract.

## API

- `POST /sessions`
- `GET /sessions/{id}`
- `PATCH /sessions/{id}`
- `POST /sessions/{id}/documents`
- `DELETE /sessions/{id}/documents/{document_id}`
- `POST /sessions/{id}/messages`
- `GET /sessions/{id}/traces`
- `GET /sessions/{id}/traces/{turn_id}`
# layered_content
