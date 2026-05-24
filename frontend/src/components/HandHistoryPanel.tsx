import type { HistoryEventView } from "../types";

interface HandHistoryPanelProps {
  events: HistoryEventView[];
}

function formatAction(action?: string | null): string {
  if (!action) {
    return "Action";
  }
  return action === "all_in" ? "all-in" : action;
}

function formatSeat(seat?: number | null, name?: string | null): string {
  if (name) {
    return name;
  }
  return typeof seat === "number" ? `Seat ${seat + 1}` : "Table";
}

function formatWinners(winners?: number[] | null): string {
  if (!winners?.length) {
    return "No winners";
  }
  return winners.map((seat) => `Seat ${seat + 1}`).join(", ");
}

function eventTitle(event: HistoryEventView): string {
  switch (event.type) {
    case "hand_started":
      return `Hand ${event.hand_number ?? ""} started`;
    case "blind":
      return `${formatSeat(event.seat)} posted ${event.blind === "small_blind" ? "small blind" : "big blind"}`;
    case "deal":
      return event.cards === "hole" ? "Hole cards dealt" : "Cards dealt";
    case "action":
      return `${formatSeat(event.seat)} ${formatAction(event.action)}`;
    case "street":
      return `${event.street ?? "Street"} dealt`;
    case "showdown":
      return `Showdown: ${formatWinners(event.winners)}`;
    case "settlement":
      return `${formatWinners(event.winners)} won ${event.pot ?? 0}`;
    case "ai_decision":
      return `${formatSeat(event.seat, event.name)} chose ${formatAction(event.action)}`;
    default:
      return event.type.split("_").join(" ");
  }
}

function eventDetail(event: HistoryEventView): string {
  switch (event.type) {
    case "hand_started":
      return `Dealer seat ${(event.dealer_seat ?? 0) + 1}`;
    case "blind":
      return `Amount ${event.amount ?? 0}`;
    case "action":
      return `${event.street ?? "street"} / amount ${event.amount ?? 0}`;
    case "street":
      return `Board cards ${event.board_count ?? 0}`;
    case "showdown":
      return event.ranks ? "Ranks evaluated" : "No rank detail";
    case "settlement": {
      const chips = event.reason === "fold" ? "fold winner" : `share ${event.share ?? 0}`;
      return event.remainder ? `${chips}, remainder ${event.remainder}` : chips;
    }
    case "ai_decision": {
      const confidence =
        typeof event.confidence === "number" ? `${Math.round(event.confidence * 100)}%` : "n/a";
      return `${event.style ?? "style pending"} / ${confidence}`;
    }
    default:
      return event.street ?? "Logged";
  }
}

export function HandHistoryPanel({ events }: HandHistoryPanelProps) {
  return (
    <section className="panel history-panel" aria-label="Hand history">
      <div className="panel-heading">
        <div>
          <h2>History</h2>
          <span>{events.length} events</span>
        </div>
      </div>

      {events.length > 0 ? (
        <ol className="history-list">
          {events.map((event, index) => (
            <li className="history-event" key={`${event.type}-${index}`}>
              <span className="history-index">{index + 1}</span>
              <div>
                <strong>{eventTitle(event)}</strong>
                <span>{eventDetail(event)}</span>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <span className="muted-state">No hand history</span>
      )}
    </section>
  );
}
