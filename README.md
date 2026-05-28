# Texas Hold'em Trainer

Local single-machine Texas Hold'em trainer for daily decision practice. One human player can train against configurable AI seats while the backend enforces poker rules deterministically and records AI reasoning for review.

This project is local-only training software. It does not support real money, payments, online matchmaking, or gambling workflows.

## Current Scope

- One human player and configurable AI opponents.
- Deterministic backend rule engine for shuffling, dealing, blinds, legal actions, betting rounds, showdown, settlement, and hand history.
- AI decision layer with local heuristic fallback, OpenAI-compatible LLM provider support, and an optional human-action reviewer.
- React/Vite frontend showing the table, stacks, bets, pot, board, hero cards, legal actions, hand history, AI reasoning, and human decision feedback.
- MVP all-in support is intentionally limited; full side-pot handling is a follow-up milestone.

## Setup

Use Python 3.11+ and Node.js 20+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cd frontend
npm install
```

## Run Locally

Start the backend from the repository root:

```bash
cd /path/to/texas_holdem
source .venv/bin/activate
PYTHONPATH="$PWD/backend" python -m uvicorn texas_holdem_trainer.api.app:app --reload --reload-dir "$PWD/backend" --port 8000
```

Start the frontend in another terminal:

```bash
cd frontend
npm run dev
```

Open the Vite URL, usually `http://127.0.0.1:5173`.

If port `8000` is already in use, start the backend on another port and point the Vite proxy to it:

```bash
cd /path/to/texas_holdem
PYTHONPATH="$PWD/backend" python -m uvicorn texas_holdem_trainer.api.app:app --reload --reload-dir "$PWD/backend" --port 8001
cd frontend
VITE_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
```

## Usage Guide

See [docs/usage.md](docs/usage.md) for the detailed Chinese usage guide. It covers the first training session, UI panels, legal actions, AI styles, LLM provider setup, verification commands, troubleshooting, and current MVP limitations.

## AI Providers

The trainer works without any API keys. AI seats use the local heuristic provider by default, and failed or invalid LLM responses fall back to the heuristic provider.

For LLM-backed experiments, copy `.env.example` to `.env` and set provider keys:

```bash
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
LLM_TIMEOUT_SECONDS=12
AI_PLAYERS_CONFIG=config/ai_players.yaml
AI_DEFAULT_PROVIDER=heuristic
```

Then copy `config/ai_players.example.yaml` to `config/ai_players.yaml` and set a bot profile provider to `openai` or `deepseek`, or set `AI_DEFAULT_PROVIDER=openai` to use that configured provider for styles without an explicit profile override. Providers without an API key are skipped and those bots fall back to heuristic play.

LLMs only choose an AI player's action, explain it, or review a human player's submitted action. Legal actions, winners, chip movement, and all poker rules remain enforced by backend code.

## Verification

Run backend tests:

```bash
python -m pytest -q
```

Build the frontend:

```bash
cd frontend
npm run build
```

Manual smoke test:

1. Create a table.
2. Start a hand.
3. Confirm human legal actions are visible only on the human turn.
4. Submit an action.
5. Confirm the coach panel shows human decision feedback.
6. Confirm AI actions appear and the coach panel shows reasoning.
7. Confirm hand history updates as the hand progresses.

## Development Notes

- Backend package source is under `backend/texas_holdem_trainer`.
- Frontend source is under `frontend/src`.
- The FastAPI app exposes REST endpoints under `/api` and a table WebSocket under `/ws/table/{table_id}`.
- The frontend dev server proxies `/api` and `/ws` to `http://127.0.0.1:8000`.
