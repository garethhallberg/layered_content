# How the Layered Context Document Analyst Works

This application demonstrates a simple idea:

> A useful chat system does not have to send the entire conversation back to the model on every turn.

Most basic chatbots are built as an ever-growing transcript. The first user message is sent to the model. Then the assistant answer is appended. Then the next user message is appended. After 30 turns, every request contains all 30 turns. After 100 turns, every request contains all 100 turns.

That design is easy to understand, but it has three problems:

1. The prompt gets larger every turn.
2. Latency and cost tend to rise as the model reads more text.
3. Important current context gets mixed with stale context.

This app shows a different design. It still stores the full session in SQLite so the browser can reload it later, but it does not always send the full session to the model. Instead, it builds a short, labelled set of context layers for each turn.

The point of the app is not that this exact layering is perfect. The point is that the prompt should be assembled deliberately, and the user should be able to inspect what was sent.

## The Big Picture

The app has two modes:

- **Layered mode**: sends a fixed set of context layers.
- **Naive mode**: sends the system prompt, documents, and the full chat history.

Layered mode is the architecture being demonstrated. Naive mode is the comparison baseline.

The important difference is this:

```text
Naive mode:

system prompt
documents
user turn 1
assistant turn 1
user turn 2
assistant turn 2
...
latest user turn
```

```text
Layered mode:

L1 system constraints
L2 document context
L3 rolling summary
L4 recent turns
L5 working state for this turn
```

The frontend exposes those layers in the **Layer Inspector**. That inspector is the centre of the product. It shows the exact prompt structure that the backend assembled for a model call.

## CAG, Not RAG

This app is a **context-augmented generation** demo, not a retrieval-augmented generation system.

Uploaded documents are stored in the session and inserted directly into `L2_documents`. There is no vector database, no embeddings, no chunk search, and no retrieval ranking.

That is intentional. The article is about how to manage context, not how to retrieve evidence.

A future RAG version could keep the same layering pattern. In that version, `L2_documents` would contain retrieved excerpts rather than the full uploaded documents. The principle would stay the same: the app should still expose what context was selected, why it was selected, and how much it costs in tokens.

## Backend and Frontend

The backend is a FastAPI app in `backend/app/`.

The frontend is a React/Vite app in `frontend/src/`.

SQLite stores sessions, documents, turns, summaries, and traces. Docker Compose starts both parts locally:

```text
frontend  http://localhost:3000
backend   http://localhost:8000
sqlite    ./data/layered_context.db
```

The main backend entry point is `backend/app/main.py`. The most important endpoint is:

```text
POST /sessions/{session_id}/messages
```

That endpoint receives a user message, builds the prompt layers, calls the model, saves the assistant response, and stores a trace of what was sent.

## The Core Data Model

The SQLAlchemy models live in `backend/app/persistence/models.py`.

The important tables are:

- `sessions`: one conversation session.
- `documents`: uploaded PDFs, text files, or Markdown files.
- `turns`: user and assistant messages.
- `summaries`: rolling summaries of older turns.
- `traces`: the exact context layers assembled for each model call.

The full chat history is persisted in `turns`. That is storage.

The prompt sent to the model is built from selected layers. That is context.

That distinction matters. The app does not delete old turns just because they stop being sent in full. It keeps them so the session can be restored and inspected later.

## What Happens When a User Sends a Message

The request flow is in `send_message()` in `backend/app/main.py`.

At a high level:

1. Load the session.
2. Validate the message.
3. Create a new user turn in the database transaction.
4. If in layered mode, check whether summarisation should run.
5. Assemble the prompt layers.
6. Call the selected LLM provider.
7. Save the assistant turn.
8. Save a trace containing the exact assembled layers.
9. Return the assistant answer and trace to the frontend.

One implementation detail matters here: the user turn is flushed to the database before prompt assembly, but not committed until the model call succeeds. If the provider fails, the transaction is rolled back. That prevents a failed request from leaving a dangling user message with no assistant response.

## The Layer Contract

Each layer returns the same kind of object:

```python
@dataclass
class LayerOutput:
    name: str
    role: Literal["system", "user", "assistant"]
    content: str
    token_count: int
    metadata: dict
```

This is defined in `backend/app/layers/base.py`.

The `content` becomes part of the actual prompt. The `metadata` is extra information for the UI. For example, `L2_documents` stores document names in metadata, and `L5_working` stores the planner JSON.

`backend/app/assembly.py` is where the layers are composed. In layered mode it builds:

```python
[
    L1SystemLayer(),
    L2DocumentsLayer(),
    L3SummaryLayer(),
    L4RecentLayer(include_current=False),
    L5WorkingLayer(),
]
```

In naive mode it builds:

```python
[
    L1SystemLayer(),
    L2DocumentsLayer(),
    L4RecentLayer(include_all=True, include_current=True),
]
```

That is the whole architectural comparison in one place.

## L1: System Constraints

File: `backend/app/layers/l1_system.py`

`L1_system` contains the system prompt. It tells the model what role it is playing and how it should answer.

In this app, the default system prompt says the assistant is a document analyst for a teaching demo. It also says to answer from the uploaded documents and visible conversation context.

This layer is permanent for the session. It is set when the session is created and does not change on every turn.

Why it exists:

- It keeps stable behavioural rules separate from user conversation.
- It makes it obvious what high-level instructions the model received.
- It gives the UI a clear place to show system-level constraints.

## L2: Document Context

File: `backend/app/layers/l2_documents.py`

`L2_documents` contains the uploaded documents for the session. Documents are parsed in `backend/app/document_parser.py`.

Supported uploads:

- PDF
- `.txt`
- `.md`

The current implementation inserts the document content directly into the prompt:

```text
Document: beers.txt
---
content here
```

Why it exists:

- It separates document evidence from chat history.
- It makes document context inspectable.
- It lets token usage for documents be measured separately from conversation tokens.

In a RAG version, this would be the layer most likely to change. Instead of full documents, it would contain retrieved chunks.

## L3: Rolling Summary

Files:

- `backend/app/layers/l3_summary.py`
- `backend/app/summariser.py`

`L3_summary` is the compressed memory of older conversation turns.

The app keeps only a limited number of recent turns verbatim in `L4_recent`. When older turns fall out of that recent window, they become candidates for summarisation.

The summariser looks for complete user/assistant pairs that:

- are no longer in the recent window;
- have not already been covered by a previous summary.

When enough pending pairs exist, the app makes a separate model call asking for a 2-4 sentence summary. That summary is stored in the `summaries` table and appears in `L3_summary` on later turns.

By default:

- `RECENT_TURN_COUNT=6`
- `SUMMARY_THRESHOLD_PAIRS=4`
- `SUMMARY_BATCH_PAIRS=4`

That means the app keeps the last six messages verbatim, then summarises older user/assistant pairs in batches.

Why it exists:

- It keeps older context available without replaying every old message.
- It compresses decisions, facts, and open threads.
- It makes the tradeoff visible: older context is preserved, but not verbatim.

This is not magic memory. A summary can lose details. The point is that the loss is deliberate and visible.

## L4: Recent Turns

File: `backend/app/layers/l4_recent.py`

`L4_recent` is the sliding verbatim window of conversation.

In layered mode, it contains recent history but excludes the current user question. The current question appears in `L5_working`, so including it in `L4_recent` would duplicate it.

In naive mode, `L4_recent` is used differently. It includes all turns, including the current user message. This is what makes naive mode a full-history replay.

Layered mode:

```text
last N previous turns
```

Naive mode:

```text
every turn in the session
```

Why it exists:

- Recent dialogue often matters most.
- Verbatim text is useful for local continuity.
- Keeping it bounded prevents the prompt from growing forever.

The metadata also marks turns that are close to aging out of the recent window. The UI can use that to show what is about to stop being sent verbatim.

## L5: Working State

File: `backend/app/layers/l5_working.py`

`L5_working` is the per-turn scratchpad.

Before the main answer call, the app makes a smaller planner call. That planner receives:

- the current user question;
- the already-built layers `L1` through `L4`.

It returns JSON with this shape:

```json
{
  "intent": "string",
  "sub_questions": ["string"],
  "relevant_doc_sections": ["string"]
}
```

The app then renders that JSON into prose and inserts it as `L5_working`.

`L5_working` also includes:

- the current question;
- extracted entities;
- a short list of document observations.

Why it exists:

- It makes the model's current interpretation visible.
- It keeps the answer focused on the latest task.
- It gives the UI something concrete to show as "working memory".

This layer is rebuilt every turn. It is not persisted as future memory. The trace is persisted for observability, but the next model call gets a freshly-built `L5_working`.

## Why Layered Mode Uses Fewer Tokens

The key is that `L4_recent` is bounded.

In naive mode, the model sees:

```text
all previous user messages
all previous assistant messages
the latest user message
```

That prompt grows linearly with the conversation.

In layered mode, the model sees:

```text
fixed system prompt
documents
rolling summary
last N recent turns
fresh working state
```

The document layer can still be large. This app is not claiming otherwise. But the conversation part no longer grows without limit. Older dialogue is compressed into `L3_summary`, and only recent dialogue remains verbatim in `L4_recent`.

That is the performance argument:

- fewer repeated tokens;
- less stale context;
- lower prompt-processing latency as the chat grows;
- lower cost for long sessions.

The app records token counts per layer so this can be seen rather than merely asserted.

## What the Trace Is

Every message call creates a trace. A trace is a JSON record of the final prompt layers.

It includes:

- mode;
- provider;
- model;
- each layer name;
- each layer role;
- each layer content;
- token count per layer;
- total prompt tokens;
- latency;
- summariser event details if summarisation fired.

Traces are stored in the `traces` table.

This is what powers the Layer Inspector. It also means the user can select an earlier turn in the UI and see what was sent at that time.

That is important for the article. The app is not just saying "layering is better". It shows the exact context that produced each answer.

## Provider Adapters

The provider abstraction is in `backend/app/providers/base.py`.

Every provider implements:

```python
def complete(messages, *, model, max_tokens) -> Completion
def count_tokens(text, *, model) -> int
```

There are adapters for:

- OpenAI
- Anthropic
- Mistral

The app selects a provider from environment variables:

```text
LLM_PROVIDER=openai
LLM_MODEL=gpt-5-mini
```

The adapters hide provider-specific differences. For example:

- OpenAI chat completions use role-based messages and `max_completion_tokens`.
- Anthropic uses a separate system parameter.
- Mistral uses its own chat completions endpoint.

The rest of the app calls `provider.complete(...)` and does not need to know those details.

If no API key is configured, the provider returns a deterministic offline/demo response. That keeps the app usable for local exploration, but real model behaviour requires provider API keys.

## Token Counting

Each layer records a token count.

The provider is responsible for counting tokens:

```python
provider.count_tokens(content, model=session.model)
```

OpenAI uses `tiktoken` where possible. Other providers currently use a rough fallback counter. The important design point is that token counting is attached to the provider abstraction, because different providers count slightly differently.

The UI displays:

- total prompt tokens;
- tokens per layer;
- token trends over turns;
- layered vs naive growth.

This is how the demo makes prompt bloat visible.

## The Frontend

The frontend lives in `frontend/src/`.

The main file is `frontend/src/main.tsx`.

The important components are:

- `DocumentManager.tsx`: upload and remove documents.
- `ChatPane.tsx`: chat transcript and message input.
- `LayerInspector.tsx`: inspect the trace for the selected turn.
- `MetricsPanel.tsx`: token and latency metrics.
- `ModeToggle.tsx`: switch between layered and naive mode.

The frontend stores the session id in the URL and local storage. That means reloading the browser can restore the same session.

The Layer Inspector is the central teaching tool. It shows each layer as a collapsible block with:

- layer name;
- one-line description;
- token count;
- full content;
- metadata such as summary coverage or planner JSON.

## Persistence and Reloading

The session is stored in SQLite, not just browser state.

That means:

- uploaded documents survive a browser refresh;
- turns survive a browser refresh;
- summaries survive a browser refresh;
- traces survive a browser refresh.

The frontend can reload `/sessions/{id}` and reconstruct the whole view.

This matters because the app is a teaching and article-support tool. You can build a 30-turn session, close the browser, reopen it, and still inspect how the context evolved.

## Why This Is Not Just a UI Trick

The Layer Inspector is not showing a simulation. It renders the trace produced by `assembly.py`, and that trace comes from the same `LayerOutput` objects used to create the model messages.

In other words:

```text
LayerOutput objects
        |
        |--> messages sent to model
        |
        |--> trace saved for UI
```

The UI and the model call share the same source of truth.

That is the strongest part of the design. Observability is not added after the fact. It is built into prompt assembly.

## A Concrete Example

Imagine the user uploads a document called `beers.txt`, then asks 30 questions about it.

In naive mode, turn 30 sends:

```text
system prompt
beers.txt
question 1
answer 1
question 2
answer 2
...
question 30
```

In layered mode, turn 30 sends something closer to:

```text
L1: answer like a document analyst
L2: beers.txt
L3: earlier discussion summary
L4: the last six messages
L5: current task, sub-questions, relevant sections
```

The user can inspect both traces in the UI. The metrics panel should show the naive prompt ballooning faster than the layered prompt.

## Tradeoffs

Layering improves control, but it does not remove all hard problems.

Important tradeoffs:

- Summaries can lose details.
- Full document insertion does not scale to very large document collections.
- Planner calls add a small extra model call in layered mode.
- Token counting differs between providers.
- The current app is single-user and local-first.

Those tradeoffs are acceptable here because the app is a reference implementation for an article. It optimises for clarity and observability over production complexity.

## The Article Argument

The argument this app supports is:

> Long context is not the same thing as memory.

A model can accept a long prompt, but that does not mean the application should keep dumping every old message into it.

Memory is an application design problem. The app must decide:

- what is permanent;
- what is document evidence;
- what should be summarised;
- what should remain verbatim;
- what is only relevant to the current turn.

This app names those decisions as layers. Then it shows them.

That is the core idea.

