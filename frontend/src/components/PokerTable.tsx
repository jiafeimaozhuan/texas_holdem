import type { CSSProperties } from "react";
import type { TableStateResponse } from "../types";
import { CommunityCards } from "./CommunityCards";
import { PlayerSeat } from "./PlayerSeat";

interface PokerTableProps {
  state: TableStateResponse | null;
  seatStyles: Record<number, string>;
}

function blindMap(state: TableStateResponse): Record<number, string> {
  return state.history_events.reduce<Record<number, string>>((accumulator, event) => {
    if (event.type === "blind" && typeof event.seat === "number" && event.blind) {
      accumulator[event.seat] = event.blind;
    }
    return accumulator;
  }, {});
}

function seatPosition(index: number, total: number): CSSProperties {
  const angle = Math.PI / 2 + (index / total) * Math.PI * 2;
  const x = 50 + Math.cos(angle) * 45;
  const y = 50 + Math.sin(angle) * 42;

  return {
    "--seat-x": `${x}%`,
    "--seat-y": `${y}%`,
  } as CSSProperties;
}

export function PokerTable({ state, seatStyles }: PokerTableProps) {
  if (!state) {
    return (
      <section className="table-stage table-stage--empty" aria-label="Poker table">
        <div className="felt-table">
          <div className="table-center table-center--empty">
            <span>Table not created</span>
          </div>
        </div>
      </section>
    );
  }

  const blinds = blindMap(state);
  const players = [...state.players].sort((left, right) => left.seat - right.seat);

  return (
    <section className="table-stage" aria-label="Poker table">
      <div className="felt-table">
        <div className="table-center">
          <div className="pot-stack">
            <span>Pot</span>
            <strong>{state.pot}</strong>
          </div>
          <CommunityCards cards={state.board} />
          <div className="table-state-row">
            <span>{state.street}</span>
            <span>Bet {state.current_bet}</span>
            <span>Raise {state.min_raise}</span>
          </div>
        </div>

        {players.map((player, index) => (
          <div
            className="seat-position"
            key={player.seat}
            style={seatPosition(index, players.length)}
          >
            <PlayerSeat
              player={player}
              isDealer={player.seat === state.dealer_seat}
              blind={blinds[player.seat]}
              isActor={player.seat === state.current_actor_seat}
              styleLabel={seatStyles[player.seat]}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
