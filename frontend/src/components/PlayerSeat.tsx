import type { PlayerView } from "../types";
import { PlayingCard } from "./CommunityCards";

interface PlayerSeatProps {
  player: PlayerView;
  isDealer: boolean;
  blind?: string;
  isActor: boolean;
  styleLabel?: string;
}

function formatStyle(styleLabel?: string): string {
  if (!styleLabel) {
    return "Style pending";
  }
  if (styleLabel === "human") {
    return "Human";
  }
  return styleLabel
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatBlind(blind: string): string {
  if (blind === "small_blind") {
    return "SB";
  }
  if (blind === "big_blind") {
    return "BB";
  }
  return blind.toUpperCase();
}

export function PlayerSeat({
  player,
  isDealer,
  blind,
  isActor,
  styleLabel,
}: PlayerSeatProps) {
  const hiddenCards = player.hole_cards == null;
  const seatClasses = [
    "player-seat",
    player.is_human ? "player-seat--human" : "",
    player.folded ? "player-seat--folded" : "",
    player.all_in ? "player-seat--all-in" : "",
    isActor ? "player-seat--actor" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article className={seatClasses} aria-label={`${player.name}, seat ${player.seat}`}>
      <div className="seat-topline">
        <span className="seat-number">Seat {player.seat + 1}</span>
        <span className="seat-badges">
          {isDealer ? <span className="badge badge--dealer">D</span> : null}
          {blind ? <span className="badge badge--blind">{formatBlind(blind)}</span> : null}
        </span>
      </div>
      <div className="seat-name-row">
        <strong>{player.name}</strong>
        {isActor ? <span className="turn-dot" aria-label="Current actor" /> : null}
      </div>
      <span className="seat-style">{formatStyle(styleLabel)}</span>
      <div className="hole-cards" aria-label={hiddenCards ? "Hidden hole cards" : "Hole cards"}>
        <PlayingCard card={player.hole_cards?.[0]} hidden={hiddenCards} />
        <PlayingCard card={player.hole_cards?.[1]} hidden={hiddenCards} />
      </div>
      <dl className="seat-metrics">
        <div>
          <dt>Stack</dt>
          <dd>{player.stack}</dd>
        </div>
        <div>
          <dt>Bet</dt>
          <dd>{player.street_bet}</dd>
        </div>
      </dl>
      <div className="seat-state">
        {player.folded ? <span>Folded</span> : null}
        {player.all_in ? <span>All-in</span> : null}
        {!player.folded && !player.all_in ? <span>In hand</span> : null}
      </div>
    </article>
  );
}
