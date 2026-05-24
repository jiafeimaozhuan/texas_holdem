import type { CSSProperties } from "react";
import { streetLabel } from "../labels";
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
      <section className="table-stage table-stage--empty" aria-label="牌桌">
        <div className="felt-table">
          <div className="table-center table-center--empty">
            <span>尚未创建牌桌</span>
          </div>
        </div>
      </section>
    );
  }

  const blinds = blindMap(state);
  const players = [...state.players].sort((left, right) => left.seat - right.seat);

  return (
    <section className="table-stage" aria-label="牌桌">
      <div className="felt-table">
        <div className="table-center">
          <div className="pot-stack">
            <span>底池</span>
            <strong>{state.pot}</strong>
          </div>
          <CommunityCards cards={state.board} />
          <div className="table-state-row">
            <span>{streetLabel(state.street)}</span>
            <span>当前下注 {state.current_bet}</span>
            <span>最小加注 {state.min_raise}</span>
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
