import { useEffect, useMemo, useState } from "react";
import {
  connectTableSocket,
  createTable,
  startHand,
  submitAction,
  updateBots,
} from "./api/client";
import { ActionControls } from "./components/ActionControls";
import { CoachPanel } from "./components/CoachPanel";
import { HandHistoryPanel } from "./components/HandHistoryPanel";
import { PokerTable } from "./components/PokerTable";
import { SettingsPanel } from "./components/SettingsPanel";
import type {
  ActionType,
  BotStyle,
  CreateTableRequest,
  TableStateResponse,
} from "./types";

const defaultBotStyles: BotStyle[] = [
  "tight_aggressive",
  "loose_aggressive",
  "conservative",
  "bluff_heavy",
  "gto_leaning",
];

const defaultTableRequest: CreateTableRequest = {
  human_name: "Hero",
  bot_count: 3,
  bot_styles: defaultBotStyles.slice(0, 3),
  starting_stack: 1000,
  small_blind: 5,
  big_blind: 10,
  human_seat: 0,
  seed: null,
};

const streetOrder: Record<string, number> = {
  waiting: 0,
  preflop: 1,
  flop: 2,
  turn: 3,
  river: 4,
  showdown: 5,
  complete: 6,
};

function normalizeRequest(request: CreateTableRequest): CreateTableRequest {
  const seatCount = Math.min(9, Math.max(2, request.bot_count + 1));
  const botCount = seatCount - 1;
  const botStyles = request.bot_styles.slice(0, botCount);

  while (botStyles.length < botCount) {
    botStyles.push(defaultBotStyles[botStyles.length % defaultBotStyles.length]);
  }

  return {
    ...request,
    bot_count: botCount,
    bot_styles: botStyles,
    starting_stack: Math.max(1, Math.floor(request.starting_stack)),
    small_blind: Math.max(1, Math.floor(request.small_blind)),
    big_blind: Math.max(1, Math.floor(request.big_blind)),
    human_seat: Math.min(request.human_seat, seatCount - 1),
  };
}

function stylesBySeat(
  state: TableStateResponse,
  request: CreateTableRequest,
): Record<number, string> {
  const styles = normalizeRequest(request).bot_styles;
  let botIndex = 0;

  return state.players.reduce<Record<number, string>>((accumulator, player) => {
    if (player.is_human) {
      accumulator[player.seat] = "human";
      return accumulator;
    }

    accumulator[player.seat] = styles[botIndex % styles.length];
    botIndex += 1;
    return accumulator;
  }, {});
}

function actorStatus(state: TableStateResponse | null): string {
  if (!state) {
    return "No table";
  }
  if (state.current_actor_seat === null) {
    return "Waiting for hand";
  }
  const actor = state.players.find((player) => player.seat === state.current_actor_seat);
  return actor ? `${actor.name} to act` : `Seat ${state.current_actor_seat + 1} to act`;
}

function isStaleTableState(
  current: TableStateResponse | null,
  incoming: TableStateResponse,
): boolean {
  if (!current || current.table_id !== incoming.table_id) {
    return false;
  }
  if (incoming.hand_number !== current.hand_number) {
    return incoming.hand_number < current.hand_number;
  }
  return (streetOrder[incoming.street] ?? 0) < (streetOrder[current.street] ?? 0);
}

function App() {
  const [tableConfig, setTableConfig] =
    useState<CreateTableRequest>(defaultTableRequest);
  const [state, setState] = useState<TableStateResponse | null>(null);
  const [seatStyles, setSeatStyles] = useState<Record<number, string>>({});
  const [isCreating, setIsCreating] = useState(false);
  const [isStartingHand, setIsStartingHand] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [socketStatus, setSocketStatus] = useState("offline");
  const [error, setError] = useState<string | null>(null);

  const tableStatus = useMemo(() => actorStatus(state), [state]);
  const canStartHand = Boolean(
    state && (state.street === "waiting" || state.street === "complete"),
  );

  useEffect(() => {
    if (!state?.table_id) {
      setSocketStatus("offline");
      return;
    }

    setSocketStatus("connecting");
    let socket: WebSocket | null = null;

    try {
      socket = connectTableSocket(state.table_id, (incomingState) => {
        setState((currentState) =>
          isStaleTableState(currentState, incomingState)
            ? currentState
            : incomingState,
        );
      });
      socket.addEventListener("open", () => setSocketStatus("live"));
      socket.addEventListener("close", () => setSocketStatus("offline"));
      socket.addEventListener("error", () => setSocketStatus("offline"));
    } catch {
      setSocketStatus("offline");
    }

    return () => {
      socket?.close();
    };
  }, [state?.table_id]);

  async function handleCreateTable() {
    const request = normalizeRequest(tableConfig);
    setIsCreating(true);
    setError(null);

    try {
      const nextState = await createTable(request);
      setTableConfig(request);
      setSeatStyles(stylesBySeat(nextState, request));
      setState(nextState);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create table");
    } finally {
      setIsCreating(false);
    }
  }

  async function handleStartHand() {
    if (!state) {
      return;
    }

    const request = normalizeRequest(tableConfig);
    setIsStartingHand(true);
    setError(null);

    try {
      let tableState = state;
      if (state.street === "waiting" || state.street === "complete") {
        tableState = await updateBots(state.table_id, {
          bot_styles: request.bot_styles,
        });
        setTableConfig(request);
        setSeatStyles(stylesBySeat(tableState, request));
      }
      const nextState = await startHand(tableState.table_id);
      setState(nextState);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start hand");
    } finally {
      setIsStartingHand(false);
    }
  }

  async function handleSubmitAction(action: ActionType, amount: number) {
    if (!state) {
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const nextState = await submitAction(state.table_id, { action, amount });
      setState(nextState);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to submit action");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <h1>Texas Hold&apos;em Trainer</h1>
          <p>{tableStatus}</p>
        </div>
        <div className="header-actions">
          <span className={`socket-pill socket-pill--${socketStatus}`}>{socketStatus}</span>
          <button
            type="button"
            onClick={handleStartHand}
            disabled={!canStartHand || isStartingHand}
          >
            {isStartingHand ? "Starting..." : "Start Hand"}
          </button>
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <section className="table-summary" aria-label="Table status">
        <div>
          <span>Table</span>
          <strong>{state?.table_id ?? "-"}</strong>
        </div>
        <div>
          <span>Hand</span>
          <strong>{state?.hand_number ?? "-"}</strong>
        </div>
        <div>
          <span>Street</span>
          <strong>{state?.street ?? "-"}</strong>
        </div>
        <div>
          <span>Pot</span>
          <strong>{state?.pot ?? "-"}</strong>
        </div>
      </section>

      <div className="workspace-layout">
        <div className="table-column">
          <PokerTable state={state} seatStyles={seatStyles} />
          <ActionControls
            state={state}
            isSubmitting={isSubmitting}
            onSubmit={handleSubmitAction}
          />
        </div>

        <aside className="side-column" aria-label="Trainer panels">
          <CoachPanel events={state?.coach_events ?? []} />
          <SettingsPanel
            config={tableConfig}
            disabled={isCreating}
            providerStatus={state?.ai_provider_status ?? null}
            onChange={setTableConfig}
            onCreateTable={handleCreateTable}
          />
          <HandHistoryPanel events={state?.history_events ?? []} />
        </aside>
      </div>
    </main>
  );
}

export default App;
