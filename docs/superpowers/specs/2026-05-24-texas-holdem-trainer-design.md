# Texas Hold'em Trainer Design

Date: 2026-05-24

## Goal

Build a local single-machine Texas Hold'em training program for daily decision practice. The first version should be playable by one human user against multiple AI players, show AI reasoning after each AI decision, and keep all poker rules deterministic in code. The project does not support real money, payments, online matchmaking, or gambling functionality.

## Confirmed MVP Scope

The MVP is a playable local Web trainer:

- One real human player participates in every table.
- Two to five AI players can sit at the same table.
- Each AI player can have a configurable style, such as tight-aggressive, loose-aggressive, conservative, bluff-heavy, or GTO-leaning.
- AI players can use a real LLM provider when configured, and fall back to a local heuristic decision provider when no API key is available or the model response is unusable.
- The backend owns all game state, rule validation, AI turns, hand history, and settlement.
- The frontend displays the table, legal actions, player stacks, pot, community cards, hole cards, action order, betting activity, and AI thinking.
- MVP all-in handling may be simplified. Complete side-pot handling is a follow-up milestone, but the design keeps settlement isolated so it can be replaced without changing UI or AI contracts.

## Architecture

Use `FastAPI + React/Vite`.

FastAPI is the authoritative game server. It owns the current hand state, poker engine, action validation, AI decision loop, LLM adapters, and hand history. React renders the training interface and sends human actions to the backend. The browser never holds LLM API keys and never decides whether an action is legal.

Primary data flow:

```text
React UI
  -> human action
  -> FastAPI game service
  -> poker engine validates and applies the action
  -> AI service resolves any AI turns
  -> updated state and hand history are broadcast or fetched
  -> React UI updates the table and coach panel
```

The MVP uses REST for table setup and human commands, and WebSocket state push for table updates, AI turn sequences, AI thinking updates, and hand-complete events.

## Backend Rule Engine

The poker engine must be independent of FastAPI and LLM code so it can be tested directly. It should be split into small modules with explicit responsibilities:

- `Card` and `Deck`: represent cards, create a 52-card deck, shuffle, and deal.
- `PlayerState`: track seat, name, stack, current street contribution, total hand contribution, hole cards, folded state, all-in state, and active state.
- `GameState`: track dealer button, small blind, big blind, current street, community cards, pot, current actor, minimum raise, table seats, and hand history.
- `ActionValidator`: calculate legal actions and amount ranges from the current state. This includes `fold`, `check`, `call`, `bet`, `raise`, and `all-in`.
- `BettingRound`: apply actions, update contributions and stacks, determine when a betting round is complete, and advance `preflop -> flop -> turn -> river -> showdown`.
- `HandEvaluator`: evaluate the best five-card hand from seven cards and compare winners in code.
- `Settlement`: distribute chips at showdown or when all but one player folds. MVP supports normal pots and simplified all-in handling; full side pots are planned separately.
- `HandHistory`: record blinds, deals, player actions, AI rationale, street transitions, showdown results, and chip deltas.

Core Texas Hold'em rules are never delegated to an LLM. LLM output is only an input to the AI decision provider and must still pass backend action validation.

## AI And LLM Decision Design

AI players are configured through profiles and decision providers.

`BotProfile` defines style and behavior parameters:

- Name and seat.
- Style label, such as tight-aggressive, loose-aggressive, conservative, bluff-heavy, or GTO-leaning.
- Risk tolerance, bluff frequency, aggression tendency, calling tendency, and explanation tone.
- Preferred provider and model configuration.

`DecisionProvider` defines the decision interface. All providers return the same structured result:

```json
{
  "action": "call",
  "amount": 20,
  "confidence": 0.72,
  "reasoning": "Calling keeps the pot controlled with a medium-strength pair and acceptable pot odds.",
  "fallback_used": false,
  "fallback_reason": null
}
```

The MVP includes two providers:

- `HeuristicProvider`: local rule-based fallback that can play without network access or API keys.
- `LLMProvider`: OpenAI-compatible chat/completions adapter for providers such as GPT and DeepSeek.

LLM configuration belongs on the backend, through `.env` and a local config file such as `config/ai_players.yaml`. Configuration includes provider name, base URL, model, API key environment variable, temperature, timeout, and style profile mapping.

The LLM prompt must only include information visible to the acting AI player:

- Its own hole cards.
- Public community cards.
- Player stacks, visible bets, folded/all-in states, and action history.
- Pot size, amount to call, minimum raise, and legal action list.
- Its configured style.

The prompt must not include hidden cards from other active players. The LLM response must be JSON. If the response times out, fails to parse, omits required fields, or proposes an illegal action or amount, the backend uses `HeuristicProvider` and records the fallback reason.

AI reasoning is saved in hand history and shown in the frontend coach panel immediately after each AI action.

## Frontend Design

Use a trainer layout with the table in the center and a coach panel on the right.

The table area shows:

- Seats arranged around a poker table.
- Player names, AI style labels, stacks, current street contribution, folded/all-in state.
- Dealer, small blind, and big blind markers.
- Community cards, current street, pot, and recent action.
- Human player's hole cards.
- Current actor highlight and simple action-order timeline.

The human action area shows only backend-provided legal actions. It includes buttons for simple actions and an amount input or slider for bet/raise/all-in sizing. The frontend may improve ergonomics, but it must not infer legality independently from the backend.

The right coach panel shows:

- Latest AI decision.
- AI name, style, provider, and model.
- Chosen action and amount.
- Short reasoning text.
- Confidence, when available.
- Fallback status and reason, when fallback is used.

A hand history panel shows the current hand timeline, showdown result, and chip deltas. A settings panel supports starting a new table, choosing seat count, initial stacks, blind sizes, AI styles, and provider/model availability.

## API Surface

Initial backend endpoints will be:

- `POST /api/table`: create a local training table.
- `POST /api/table/{table_id}/hand`: start the next hand.
- `GET /api/table/{table_id}`: fetch current public and human-visible table state.
- `POST /api/table/{table_id}/action`: submit a human action.
- `GET /api/table/{table_id}/history`: fetch current or recent hand history.
- `PUT /api/table/{table_id}/bots`: update AI seats and styles between hands.

- `WS /ws/table/{table_id}`: stream table state, action events, AI thinking updates, and hand-complete events.

## Error Handling

The game should continue when AI integrations fail.

- Missing API key: use `HeuristicProvider`; show fallback in the coach panel.
- LLM timeout: use `HeuristicProvider`; record timeout as fallback reason.
- Invalid JSON: use `HeuristicProvider`; preserve the raw parse failure in logs, not necessarily in user-facing UI.
- Illegal LLM action: reject it, use `HeuristicProvider`, and record the illegal action in hand history metadata.
- Human illegal action: return a structured validation error and refresh legal actions.

## Testing Strategy

Testing priority is the deterministic rule engine.

Unit tests should cover:

- Deck creation, shuffling, and dealing.
- Hand evaluation and tie-breaking.
- Blind posting and preflop action order.
- Legal action calculation for check, call, bet, raise, fold, and all-in.
- Betting round completion and street transitions.
- Fold wins, showdown wins, split pots, and MVP all-in settlement behavior.

Integration tests should cover:

- A full hand from blinds through showdown.
- A hand ending before showdown because all but one player folded.
- AI fallback when no API key is configured.
- AI fallback when LLM output is invalid or illegal.
- Hand history contains actions, AI reasoning, showdown, and chip deltas.

Frontend verification should cover:

- Table state renders correctly.
- Legal human actions are displayed from backend state.
- Human actions submit and refresh state.
- AI thinking appears after AI decisions.
- Hand history is readable after a hand completes.

## Follow-Up Milestones

- Complete all-in side-pot creation and settlement.
- Replay and review mode for completed hands.
- AI style editor with saved profiles.
- Additional providers, such as local Ollama or Anthropic.
- Training statistics, such as VPIP, PFR, aggression factor, showdown win rate, and repeated decision leak markers.
- Import/export hand histories.

## Non-Goals

- Real money play.
- Payments.
- Online matchmaking.
- Gambling or casino workflows.
- Letting an LLM decide poker rules, winners, legal actions, or chip settlement.
