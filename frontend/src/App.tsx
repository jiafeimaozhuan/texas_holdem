import { useMemo, useState } from "react";
import { createTable, startHand } from "./api/client";
import type { CreateTableRequest, TableStateResponse } from "./types";

const defaultTableRequest: CreateTableRequest = {
  human_name: "Hero",
  bot_count: 3,
  bot_styles: ["tight_aggressive", "loose_aggressive", "conservative"],
  starting_stack: 1000,
  small_blind: 5,
  big_blind: 10,
  human_seat: 0,
  seed: null,
};

function App() {
  const [state, setState] = useState<TableStateResponse | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isStartingHand, setIsStartingHand] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tableStatus = useMemo(() => {
    if (!state) {
      return "No table";
    }

    const actor = state.players.find((player) => player.seat === state.current_actor_seat);
    return actor ? `Waiting on ${actor.name}` : "Waiting for next hand";
  }, [state]);

  async function handleCreateTable() {
    setIsCreating(true);
    setError(null);

    try {
      const nextState = await createTable(defaultTableRequest);
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

    setIsStartingHand(true);
    setError(null);

    try {
      const nextState = await startHand(state.table_id);
      setState(nextState);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start hand");
    } finally {
      setIsStartingHand(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="toolbar" aria-label="Trainer controls">
        <div>
          <h1>Texas Hold&apos;em Trainer</h1>
          <p>{tableStatus}</p>
        </div>
        <div className="actions">
          <button type="button" onClick={handleCreateTable} disabled={isCreating}>
            {isCreating ? "Creating..." : "Create Default Table"}
          </button>
          <button
            type="button"
            onClick={handleStartHand}
            disabled={!state || isStartingHand}
          >
            {isStartingHand ? "Starting..." : "Start Hand"}
          </button>
        </div>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <section className="status-grid" aria-label="Table status">
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

      <section className="state-preview" aria-label="State preview">
        <div className="section-heading">
          <h2>Latest State</h2>
          <span>{state ? `${state.players.length} players` : "No state loaded"}</span>
        </div>
        <pre>{state ? JSON.stringify(state, null, 2) : "Create a table to load state."}</pre>
      </section>
    </main>
  );
}

export default App;
