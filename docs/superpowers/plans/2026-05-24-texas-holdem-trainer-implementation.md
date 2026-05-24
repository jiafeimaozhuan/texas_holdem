# Texas Hold'em Trainer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a playable local Texas Hold'em trainer where one human plays against configurable AI players, with deterministic poker rules, LLM-backed AI decisions when configured, heuristic fallback, a FastAPI backend, and a React/Vite table UI.

**Architecture:** FastAPI is the authoritative game server and owns all poker rules, game state, AI decisions, LLM adapters, settlement, hand history, REST commands, and WebSocket state push. React renders the table and coach panel, submits only human commands, and displays backend-provided legal actions and AI reasoning.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, pytest, httpx, PyYAML, Uvicorn, TypeScript, React, Vite, CSS modules/plain CSS.

---

## File Structure

- `pyproject.toml`: backend package metadata, dependencies, pytest config.
- `.env.example`: sample local LLM configuration variables.
- `config/ai_players.example.yaml`: example bot profiles and provider config.
- `backend/texas_holdem_trainer/domain/cards.py`: card, rank, suit, and deck primitives.
- `backend/texas_holdem_trainer/domain/actions.py`: action enums, legal action ranges, action requests.
- `backend/texas_holdem_trainer/domain/state.py`: player state, game state, street state, hand history records.
- `backend/texas_holdem_trainer/domain/evaluator.py`: deterministic best-hand evaluation and tie-breaking.
- `backend/texas_holdem_trainer/domain/engine.py`: blinds, dealing, action application, betting-round flow, showdown, settlement.
- `backend/texas_holdem_trainer/ai/profiles.py`: bot style profiles.
- `backend/texas_holdem_trainer/ai/providers.py`: heuristic and LLM decision providers.
- `backend/texas_holdem_trainer/ai/service.py`: AI turn orchestration and fallback handling.
- `backend/texas_holdem_trainer/api/schemas.py`: API and WebSocket DTOs.
- `backend/texas_holdem_trainer/api/app.py`: FastAPI app, REST endpoints, WebSocket endpoint.
- `backend/texas_holdem_trainer/runtime/table_manager.py`: in-memory local table lifecycle and broadcasting.
- `tests/domain/*.py`: deterministic engine tests.
- `tests/ai/*.py`: AI provider and fallback tests.
- `tests/api/*.py`: FastAPI integration tests.
- `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`: frontend tooling.
- `frontend/src/api/client.ts`: REST and WebSocket client.
- `frontend/src/types.ts`: frontend DTO types matching backend schemas.
- `frontend/src/App.tsx`: trainer shell and state orchestration.
- `frontend/src/components/*.tsx`: table, seats, action controls, coach panel, history panel, settings.
- `frontend/src/styles.css`: responsive trainer layout.

---

## Task 1: Backend Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `config/ai_players.example.yaml`
- Create: `backend/texas_holdem_trainer/__init__.py`
- Create: `backend/texas_holdem_trainer/domain/__init__.py`
- Create: `backend/texas_holdem_trainer/ai/__init__.py`
- Create: `backend/texas_holdem_trainer/api/__init__.py`
- Create: `backend/texas_holdem_trainer/runtime/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Add backend package metadata**

Create `pyproject.toml` with:

```toml
[project]
name = "texas-holdem-trainer"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.111",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.7",
  "httpx>=0.27",
  "PyYAML>=6.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "pytest-asyncio>=0.23",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["backend"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Add safe local configuration examples**

Create `.env.example` with:

```text
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
LLM_TIMEOUT_SECONDS=12
```

Create `config/ai_players.example.yaml` with:

```yaml
providers:
  openai:
    base_url: "https://api.openai.com/v1"
    api_key_env: "OPENAI_API_KEY"
    model: "gpt-4.1-mini"
    temperature: 0.4
  deepseek:
    base_url: "https://api.deepseek.com/v1"
    api_key_env: "DEEPSEEK_API_KEY"
    model: "deepseek-chat"
    temperature: 0.4
profiles:
  - name: "TAG Bot"
    style: "tight_aggressive"
    provider: "heuristic"
  - name: "LAG Bot"
    style: "loose_aggressive"
    provider: "heuristic"
```

- [ ] **Step 3: Create package directories and empty init files**

Run: `mkdir -p backend/texas_holdem_trainer/{domain,ai,api,runtime} tests config`

Create each `__init__.py` as an empty file.

- [ ] **Step 4: Verify skeleton imports**

Run: `python -m pytest -q`

Expected: pytest runs with `no tests ran` and exits successfully after dependencies are installed.

- [ ] **Step 5: Commit**

Run:

```bash
git add pyproject.toml .env.example config/ai_players.example.yaml backend tests
git commit -m "chore: scaffold backend package"
```

---

## Task 2: Cards, Actions, And State Models

**Files:**
- Create: `backend/texas_holdem_trainer/domain/cards.py`
- Create: `backend/texas_holdem_trainer/domain/actions.py`
- Create: `backend/texas_holdem_trainer/domain/state.py`
- Test: `tests/domain/test_cards_and_state.py`

- [ ] **Step 1: Write failing tests for card and state primitives**

Create `tests/domain/test_cards_and_state.py` with tests that assert:

```python
from texas_holdem_trainer.domain.actions import ActionType, LegalAction
from texas_holdem_trainer.domain.cards import Deck, Rank, Suit
from texas_holdem_trainer.domain.state import GameState, PlayerState, Street


def test_deck_has_52_unique_cards():
    deck = Deck.new_shuffled(seed=7)
    cards = deck.cards
    assert len(cards) == 52
    assert len(set(cards)) == 52


def test_deal_removes_cards_from_deck():
    deck = Deck.new_shuffled(seed=7)
    first = deck.deal(2)
    second = deck.deal(3)
    assert len(first) == 2
    assert len(second) == 3
    assert len(deck.cards) == 47
    assert set(first).isdisjoint(second)


def test_player_state_tracks_bet_and_stack():
    player = PlayerState(seat=0, name="Hero", stack=1000, is_human=True)
    player.commit_chips(25)
    assert player.stack == 975
    assert player.street_bet == 25
    assert player.total_committed == 25


def test_game_state_active_players_excludes_folded_and_busted():
    players = [
        PlayerState(seat=0, name="Hero", stack=1000, is_human=True),
        PlayerState(seat=1, name="Bot", stack=0, folded=True),
    ]
    state = GameState(table_id="t1", players=players, dealer_seat=0, small_blind=10, big_blind=20)
    assert state.street == Street.WAITING
    assert [p.name for p in state.players_in_hand()] == ["Hero"]


def test_legal_action_represents_amount_bounds():
    action = LegalAction(type=ActionType.RAISE, min_amount=60, max_amount=300)
    assert action.type is ActionType.RAISE
    assert action.min_amount == 60
    assert action.max_amount == 300
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/domain/test_cards_and_state.py -q`

Expected: FAIL with import errors for missing domain modules.

- [ ] **Step 3: Implement primitives**

Implement:

```python
class Suit(str, Enum): CLUBS = "c"; DIAMONDS = "d"; HEARTS = "h"; SPADES = "s"
class Rank(IntEnum): TWO = 2; THREE = 3; FOUR = 4; FIVE = 5; SIX = 6; SEVEN = 7; EIGHT = 8; NINE = 9; TEN = 10; JACK = 11; QUEEN = 12; KING = 13; ACE = 14
@dataclass(frozen=True, slots=True)
class Card: rank: Rank; suit: Suit
class Deck: new_shuffled(seed: int | None = None) -> "Deck"; deal(count: int) -> list[Card]
class ActionType(str, Enum): FOLD, CHECK, CALL, BET, RAISE, ALL_IN
@dataclass(frozen=True, slots=True)
class LegalAction: type: ActionType; min_amount: int = 0; max_amount: int = 0
class Street(str, Enum): WAITING, PREFLOP, FLOP, TURN, RIVER, SHOWDOWN, COMPLETE
@dataclass
class PlayerState: commit_chips(amount: int) -> int
@dataclass
class GameState: players_in_hand() -> list[PlayerState]
```

Use integer chips only. `commit_chips` must cap at the player's stack and mark `all_in=True` when stack reaches zero.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/domain/test_cards_and_state.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/texas_holdem_trainer/domain tests/domain/test_cards_and_state.py
git commit -m "feat: add poker domain primitives"
```

---

## Task 3: Deterministic Hand Evaluator

**Files:**
- Create: `backend/texas_holdem_trainer/domain/evaluator.py`
- Test: `tests/domain/test_evaluator.py`

- [ ] **Step 1: Write evaluator tests**

Create `tests/domain/test_evaluator.py` with cases for high card, pair, two pair, trips, straight including wheel, flush, full house, quads, straight flush, ties, and kicker comparison. Use helper `c("Ah")` to parse cards.

- [ ] **Step 2: Run evaluator tests to verify failure**

Run: `python -m pytest tests/domain/test_evaluator.py -q`

Expected: FAIL because `evaluator.py` is missing.

- [ ] **Step 3: Implement evaluator**

Implement:

```python
class HandCategory(IntEnum):
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9

@dataclass(frozen=True, order=True)
class HandRank:
    category: HandCategory
    tiebreakers: tuple[int, ...]

def evaluate_best(cards: Sequence[Card]) -> HandRank:
    """Return the best five-card rank from 5 to 7 cards."""
```

Compare all five-card combinations from the input and return the max `HandRank`. This is simple and reliable for MVP because there are only 21 combinations from seven cards.

- [ ] **Step 4: Run evaluator tests**

Run: `python -m pytest tests/domain/test_evaluator.py -q`

Expected: all evaluator tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/texas_holdem_trainer/domain/evaluator.py tests/domain/test_evaluator.py
git commit -m "feat: add deterministic hand evaluator"
```

---

## Task 4: Engine Flow, Legal Actions, And Settlement

**Files:**
- Create: `backend/texas_holdem_trainer/domain/engine.py`
- Test: `tests/domain/test_engine_flow.py`
- Test: `tests/domain/test_action_validation.py`

- [ ] **Step 1: Write tests for blinds and action order**

Test that `start_hand()` posts blinds, deals two hole cards per player, sets `Street.PREFLOP`, and starts action left of the big blind for 3+ players.

- [ ] **Step 2: Write tests for legal actions**

Cover:

```python
assert legal action list contains CALL and RAISE when facing a bet
assert legal action list contains CHECK and BET when no bet is faced
assert CHECK is absent when facing a bet
assert RAISE min_amount is current bet plus minimum raise
assert ALL_IN is present whenever stack > 0
```

- [ ] **Step 3: Write tests for street progression and settlement**

Cover a hand that reaches flop, turn, river, and showdown, plus a hand ending when all but one player folds. Add one MVP all-in test that asserts all committed chips are included in a single pot and the documented simplified settlement is applied.

- [ ] **Step 4: Run engine tests to verify failure**

Run: `python -m pytest tests/domain/test_engine_flow.py tests/domain/test_action_validation.py -q`

Expected: FAIL because `engine.py` is missing.

- [ ] **Step 5: Implement engine API**

Implement these public methods:

```python
class PokerEngine:
    def create_table(self, table_id: str, player_names: list[str], human_seat: int, starting_stack: int, small_blind: int, big_blind: int, seed: int | None = None) -> GameState: ...
    def start_hand(self, state: GameState) -> GameState: ...
    def legal_actions(self, state: GameState, seat: int) -> list[LegalAction]: ...
    def apply_action(self, state: GameState, seat: int, action: ActionType, amount: int = 0) -> GameState: ...
```

Keep mutations on `GameState` for simplicity in MVP, but return the state from each method. Append hand history entries for blinds, deals, actions, street changes, showdown, and settlements.

- [ ] **Step 6: Run complete domain tests**

Run: `python -m pytest tests/domain -q`

Expected: all domain tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add backend/texas_holdem_trainer/domain tests/domain
git commit -m "feat: implement holdem engine flow"
```

---

## Task 5: AI Profiles, Heuristic Provider, And LLM Fallback Contract

**Files:**
- Create: `backend/texas_holdem_trainer/ai/profiles.py`
- Create: `backend/texas_holdem_trainer/ai/providers.py`
- Create: `backend/texas_holdem_trainer/ai/service.py`
- Test: `tests/ai/test_ai_decisions.py`

- [ ] **Step 1: Write AI tests**

Test that:

```python
HeuristicProvider returns one backend-legal action.
BotProfile style changes aggression parameters.
AIService records fallback when LLM provider raises a timeout.
AIService records fallback when LLM provider returns an illegal action.
AIService never receives hidden opponent hole cards in its visible-state prompt payload.
```

- [ ] **Step 2: Run AI tests to verify failure**

Run: `python -m pytest tests/ai/test_ai_decisions.py -q`

Expected: FAIL because AI modules are missing.

- [ ] **Step 3: Implement AI contracts**

Implement:

```python
@dataclass(frozen=True)
class BotProfile:
    name: str
    style: BotStyle
    provider: str = "heuristic"
    model: str | None = None
    risk_tolerance: float = 0.5
    bluff_frequency: float = 0.1
    aggression: float = 0.5

@dataclass(frozen=True)
class DecisionResult:
    action: ActionType
    amount: int = 0
    confidence: float = 0.5
    reasoning: str = ""
    fallback_used: bool = False
    fallback_reason: str | None = None
```

`HeuristicProvider` should prefer checking when possible, call small bets with stronger made hands or reasonable pot odds, raise/bet more often for aggressive profiles, and fold weak hands facing large bets.

- [ ] **Step 4: Implement LLM provider with strict JSON parsing**

Use `httpx.AsyncClient` against an OpenAI-compatible `/chat/completions` endpoint. Require JSON with `action`, `amount`, `confidence`, and `reasoning`. Do not log API keys. Return parsed `DecisionResult`; let `AIService` validate legality and fallback.

- [ ] **Step 5: Run AI tests**

Run: `python -m pytest tests/ai -q`

Expected: all AI tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/texas_holdem_trainer/ai tests/ai
git commit -m "feat: add ai decision providers"
```

---

## Task 6: Table Manager, API Schemas, REST, And WebSocket

**Files:**
- Create: `backend/texas_holdem_trainer/api/schemas.py`
- Create: `backend/texas_holdem_trainer/api/app.py`
- Create: `backend/texas_holdem_trainer/runtime/table_manager.py`
- Test: `tests/api/test_table_api.py`

- [ ] **Step 1: Write API integration tests**

Use `fastapi.testclient.TestClient` to verify:

```python
POST /api/table creates a table with one human and AI seats.
POST /api/table/{table_id}/hand starts a hand.
GET /api/table/{table_id} returns human-visible state, not AI hole cards.
POST /api/table/{table_id}/action rejects illegal human actions.
POST /api/table/{table_id}/action accepts a legal action and advances AI turns.
GET /api/table/{table_id}/history includes AI reasoning entries.
```

- [ ] **Step 2: Run API tests to verify failure**

Run: `python -m pytest tests/api/test_table_api.py -q`

Expected: FAIL because API modules are missing.

- [ ] **Step 3: Implement DTOs**

Define Pydantic models:

```python
CreateTableRequest, StartHandResponse, SubmitActionRequest, TableStateResponse,
PlayerView, CardView, LegalActionView, CoachEventView, HistoryEventView
```

`TableStateResponse` must include only the human player's hole cards unless the hand is complete.

- [ ] **Step 4: Implement in-memory table manager**

`TableManager` owns a dict of `table_id -> GameState`, a `PokerEngine`, and an `AIService`. It exposes `create_table`, `start_hand`, `get_state`, `submit_human_action`, `get_history`, and `subscribe`/`broadcast` helpers for WebSocket clients.

- [ ] **Step 5: Implement FastAPI app**

Create `app = FastAPI(title="Texas Hold'em Trainer")`, wire the REST endpoints from the design spec, and add `WS /ws/table/{table_id}` that sends serialized state after each broadcast.

- [ ] **Step 6: Run API tests and domain/AI tests**

Run: `python -m pytest tests -q`

Expected: all backend tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add backend/texas_holdem_trainer/api backend/texas_holdem_trainer/runtime tests/api
git commit -m "feat: expose local trainer api"
```

---

## Task 7: Frontend Scaffold And API Client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles.css`

- [ ] **Step 1: Add Vite React project files**

Use TypeScript, React 18+, and Vite. Add scripts:

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc && vite build",
    "preview": "vite preview --host 127.0.0.1"
  }
}
```

- [ ] **Step 2: Define frontend DTOs matching backend**

Create `types.ts` with `CardView`, `PlayerView`, `LegalActionView`, `CoachEventView`, `HistoryEventView`, and `TableStateResponse`.

- [ ] **Step 3: Implement API client**

Implement:

```ts
export async function createTable(request: CreateTableRequest): Promise<TableStateResponse>
export async function startHand(tableId: string): Promise<TableStateResponse>
export async function submitAction(tableId: string, request: SubmitActionRequest): Promise<TableStateResponse>
export function connectTableSocket(tableId: string, onState: (state: TableStateResponse) => void): WebSocket
```

- [ ] **Step 4: Add minimal App shell**

`App.tsx` should create a default table on user command, start a hand, hold the latest state, and render a minimal shell with table status, current street, pot size, and a JSON state preview until the full components are added in Task 8.

- [ ] **Step 5: Build frontend**

Run: `cd frontend && npm install && npm run build`

Expected: Vite build succeeds.

- [ ] **Step 6: Commit**

Run:

```bash
git add frontend
git commit -m "feat: scaffold trainer frontend"
```

---

## Task 8: Trainer UI Components

**Files:**
- Create: `frontend/src/components/PokerTable.tsx`
- Create: `frontend/src/components/PlayerSeat.tsx`
- Create: `frontend/src/components/CommunityCards.tsx`
- Create: `frontend/src/components/ActionControls.tsx`
- Create: `frontend/src/components/CoachPanel.tsx`
- Create: `frontend/src/components/HandHistoryPanel.tsx`
- Create: `frontend/src/components/SettingsPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Implement table and seat components**

Render seats around a central table. Show player name, style, stack, current bet, folded/all-in state, and dealer/blind badges. Show only cards present in `PlayerView.hole_cards`.

- [ ] **Step 2: Implement action controls**

Render backend-provided legal actions only. For `bet`, `raise`, and `all-in`, show a numeric amount control constrained by `min_amount` and `max_amount`. Disable controls when `current_actor_seat` is not the human seat.

- [ ] **Step 3: Implement coach and history panels**

Coach panel shows latest AI action, amount, confidence, reasoning, provider/model, and fallback reason. History panel lists blinds, actions, street changes, showdown, and chip deltas in chronological order.

- [ ] **Step 4: Implement settings panel**

Allow the user to choose seat count, starting stack, blinds, and bot style labels before creating a table. Keep provider configuration display-only in MVP, showing whether heuristic or LLM is configured by backend state.

- [ ] **Step 5: Build frontend**

Run: `cd frontend && npm run build`

Expected: build succeeds with no TypeScript errors.

- [ ] **Step 6: Commit**

Run:

```bash
git add frontend/src
git commit -m "feat: build trainer table ui"
```

---

## Task 9: End-To-End Local Run And Documentation

**Files:**
- Create: `README.md`
- Modify: `.gitignore`
- Verify: backend and frontend runtime

- [ ] **Step 1: Add README run instructions**

Document:

```text
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn texas_holdem_trainer.api.app:app --reload --app-dir backend --port 8000
cd frontend
npm install
npm run dev
```

Also document `.env.example`, heuristic fallback, and the non-gambling local-only scope.

- [ ] **Step 2: Run backend tests**

Run: `python -m pytest -q`

Expected: all backend tests pass.

- [ ] **Step 3: Run frontend build**

Run: `cd frontend && npm run build`

Expected: Vite build succeeds.

- [ ] **Step 4: Start backend and frontend for manual verification**

Run backend: `uvicorn texas_holdem_trainer.api.app:app --app-dir backend --port 8000`

Run frontend: `cd frontend && npm run dev`

Verify in browser:

```text
Create table -> Start hand -> human legal actions visible -> submit action -> AI actions appear -> coach panel shows reasoning -> hand history updates.
```

- [ ] **Step 5: Commit**

Run:

```bash
git add README.md .gitignore
git commit -m "docs: add local trainer runbook"
```

---

## Review Checkpoints

After each task:

- Run the exact test command listed in the task.
- Inspect `git diff --stat` before committing.
- Commit only files listed in the task unless the implementation requires a directly related import or package export.

After Task 4:

- Review rule-engine behavior before building AI and API code.
- Confirm no LLM, API, or frontend code is needed to evaluate legal actions or winners.

After Task 6:

- Confirm API responses never expose hidden AI hole cards to the human before showdown.
- Confirm illegal human and LLM actions are rejected by backend validation.

After Task 9:

- Run `git status --short` and confirm the working tree is clean.
