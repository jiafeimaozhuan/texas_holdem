import { blindLabel, seatLabel, styleLabel as formatStyleLabel } from "../labels";
import type { PlayerView } from "../types";
import { PlayingCard } from "./CommunityCards";

interface PlayerSeatProps {
  player: PlayerView;
  isDealer: boolean;
  blind?: string;
  isActor: boolean;
  styleLabel?: string;
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
    <article className={seatClasses} aria-label={`${player.name}，${seatLabel(player.seat)}`}>
      <div className="seat-topline">
        <span className="seat-number">{seatLabel(player.seat)}</span>
        <span className="seat-badges">
          {isDealer ? <span className="badge badge--dealer">庄</span> : null}
          {blind ? <span className="badge badge--blind">{blindLabel(blind)}</span> : null}
        </span>
      </div>
      <div className="seat-name-row">
        <strong>{player.name}</strong>
        {isActor ? <span className="turn-dot" aria-label="当前行动玩家" /> : null}
      </div>
      <span className="seat-style">{formatStyleLabel(styleLabel)}</span>
      <div className="hole-cards" aria-label={hiddenCards ? "隐藏手牌" : "手牌"}>
        <PlayingCard card={player.hole_cards?.[0]} hidden={hiddenCards} />
        <PlayingCard card={player.hole_cards?.[1]} hidden={hiddenCards} />
      </div>
      <dl className="seat-metrics">
        <div>
          <dt>筹码</dt>
          <dd>{player.stack}</dd>
        </div>
        <div>
          <dt>下注</dt>
          <dd>{player.street_bet}</dd>
        </div>
      </dl>
      <div className="seat-state">
        {player.folded ? <span>已弃牌</span> : null}
        {player.all_in ? <span>全下</span> : null}
        {!player.folded && !player.all_in ? <span>牌局中</span> : null}
      </div>
    </article>
  );
}
