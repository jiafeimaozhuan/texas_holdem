# Repository Guidelines

## Project Structure & Module Organization

This repository is a local Texas Hold'em trainer with a Python backend and React frontend.

- `backend/texas_holdem_trainer/`: FastAPI app, runtime orchestration, AI providers, and deterministic poker domain logic.
- `backend/texas_holdem_trainer/domain/`: rule engine, cards, actions, game state, and hand evaluator. Poker rules belong here, not in LLM prompts.
- `frontend/src/`: React/Vite UI components, API client, labels, shared types, and styling.
- `tests/`: pytest suites for domain, AI, runtime config, and API behavior.
- `config/`: AI provider/profile YAML files.
- `docs/`: usage notes and design/planning documents.

## Build, Test, and Development Commands

Install backend dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run backend locally from the repository root:

```bash
PYTHONPATH="$PWD/backend" python -m uvicorn texas_holdem_trainer.api.app:app --reload --reload-dir "$PWD/backend" --port 8000
```

Install and run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Verify backend and frontend:

```bash
python -m pytest -q
cd frontend && npm run build
```

## Coding Style & Naming Conventions

Use Python 3.11+ typing and small, explicit modules. Keep deterministic poker rules in code and LLM behavior in `backend/texas_holdem_trainer/ai/`. Prefer dataclasses or Pydantic models for structured data. Frontend components use PascalCase filenames, TypeScript interfaces, and centralized display labels in `frontend/src/labels.ts`.

## Testing Guidelines

Tests use pytest and pytest-asyncio. Name files `test_*.py` and keep tests near the behavior they cover: domain rules in `tests/domain/`, API flows in `tests/api/`, AI provider behavior in `tests/ai/`. Add regression tests for rule changes, provider fallbacks, and UI/API contract changes. Run `python -m pytest -q` before committing.

## Commit & Pull Request Guidelines

Commit history follows concise conventional prefixes, for example `feat: add human decision reviewer`, `fix: recycle codex app server sessions`, and `docs: clarify backend command working directory`. Keep commits focused and describe the user-visible change. Pull requests should include a short summary, verification commands run, related issue or context, and screenshots for UI layout changes.

## Security & Configuration Tips

Do not commit real API keys. Use `.env` for secrets and `config/ai_players.example.yaml` for shareable provider examples. LLMs may choose actions or review decisions, but legal actions, showdown, chip settlement, and hand history must remain backend-enforced.
