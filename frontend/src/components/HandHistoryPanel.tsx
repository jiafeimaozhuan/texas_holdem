import { actionLabel, blindLabel, seatLabel, streetLabel, styleLabel } from "../labels";
import type { HistoryEventView } from "../types";

interface HandHistoryPanelProps {
  events: HistoryEventView[];
}

function formatAction(action?: string | null): string {
  return actionLabel(action);
}

function formatSeat(seat?: number | null, name?: string | null): string {
  if (name) {
    return name;
  }
  return seatLabel(seat);
}

function formatWinners(winners?: number[] | null): string {
  if (!winners?.length) {
    return "无赢家";
  }
  return winners.map((seat) => seatLabel(seat)).join(", ");
}

function eventTitle(event: HistoryEventView): string {
  switch (event.type) {
    case "hand_started":
      return `第 ${event.hand_number ?? ""} 手牌开始`;
    case "blind":
      return `${formatSeat(event.seat)} 下注${blindLabel(event.blind)}`;
    case "deal":
      return event.cards === "hole" ? "手牌已发" : "牌已发";
    case "action":
      return `${formatSeat(event.seat)} ${formatAction(event.action)}`;
    case "street":
      return `${streetLabel(event.street)}已发`;
    case "showdown":
      return `摊牌：${formatWinners(event.winners)}`;
    case "settlement":
      return `${formatWinners(event.winners)} 赢得 ${event.pot ?? 0}`;
    case "ai_decision":
      return `${formatSeat(event.seat, event.name)} 选择${formatAction(event.action)}`;
    default:
      return event.type.split("_").join(" ");
  }
}

function eventDetail(event: HistoryEventView): string {
  switch (event.type) {
    case "hand_started":
      return `庄位 ${seatLabel(event.dealer_seat)}`;
    case "blind":
      return `金额 ${event.amount ?? 0}`;
    case "action":
      return `${streetLabel(event.street)} / 金额 ${event.amount ?? 0}`;
    case "street":
      return `公共牌 ${event.board_count ?? 0} 张`;
    case "showdown":
      return event.ranks ? "牌力已评估" : "无牌力详情";
    case "settlement": {
      const chips = event.reason === "fold" ? "其他玩家弃牌获胜" : `分得 ${event.share ?? 0}`;
      return event.remainder ? `${chips}，余数 ${event.remainder}` : chips;
    }
    case "ai_decision": {
      const confidence =
        typeof event.confidence === "number" ? `${Math.round(event.confidence * 100)}%` : "n/a";
      return `${styleLabel(event.style)} / ${confidence}`;
    }
    default:
      return event.street ? streetLabel(event.street) : "已记录";
  }
}

export function HandHistoryPanel({ events }: HandHistoryPanelProps) {
  return (
    <section className="panel history-panel" aria-label="手牌历史">
      <div className="panel-heading">
        <div>
          <h2>历史</h2>
          <span>{events.length} 条事件</span>
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
        <span className="muted-state">暂无手牌历史</span>
      )}
    </section>
  );
}
