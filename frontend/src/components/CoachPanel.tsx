import {
  actionWithAmount,
  fallbackReasonLabel,
  modelLabel,
  providerLabel,
  streetLabel,
  styleLabel,
} from "../labels";
import type { CoachEventView, HumanReviewEventView } from "../types";

interface CoachPanelProps {
  events: CoachEventView[];
  reviewEvents: HumanReviewEventView[];
  selectedSeat: number | null;
  selectedPlayerName?: string | null;
  onClearSelection: () => void;
}

function formatAction(event: CoachEventView): string {
  return actionWithAmount(event.action, event.amount);
}

function displayedReasoning(event: CoachEventView): string {
  if (event.provider !== "heuristic" && event.source_reasoning?.trim()) {
    return event.source_reasoning.trim();
  }
  return event.reasoning;
}

function reasoningTitle(event: CoachEventView): string {
  return event.provider === "heuristic" ? "决策说明" : "LLM 返回思考";
}

export function CoachPanel({
  events,
  reviewEvents,
  selectedSeat,
  selectedPlayerName,
  onClearSelection,
}: CoachPanelProps) {
  const latest =
    selectedSeat == null
      ? events[events.length - 1]
      : [...events].reverse().find((event) => event.seat === selectedSeat);
  const isFiltered = selectedSeat != null;
  const latestReview = reviewEvents[reviewEvents.length - 1];

  return (
    <section className="panel coach-panel" aria-label="教练面板">
      <div className="panel-heading">
        <div>
          <h2>教练</h2>
          <span>
            {isFiltered
              ? `查看 ${selectedPlayerName ?? "电脑玩家"}`
              : latest
                ? `第 ${latest.hand_number} 手 / ${streetLabel(latest.street)}`
                : "空闲"}
          </span>
        </div>
        {isFiltered ? (
          <button type="button" className="text-button" onClick={onClearSelection}>
            查看最新
          </button>
        ) : null}
      </div>

      {latest ? (
        <div className="coach-content">
          <div className="coach-action">
            <span>{latest.name}</span>
            <strong>{formatAction(latest)}</strong>
          </div>

          <dl className="coach-metrics">
            <div>
              <dt>风格</dt>
              <dd>{styleLabel(latest.style)}</dd>
            </div>
            <div>
              <dt>决策源</dt>
              <dd>{providerLabel(latest.provider)}</dd>
            </div>
            <div>
              <dt>模型</dt>
              <dd>{modelLabel(latest.model)}</dd>
            </div>
            <div>
              <dt>置信度</dt>
              <dd>{Math.round(latest.confidence * 100)}%</dd>
            </div>
            <div>
              <dt>状态</dt>
              <dd>{latest.fallback_used ? "已回退" : "主决策"}</dd>
            </div>
          </dl>

          <div className="coach-reasoning-block">
            <span>{reasoningTitle(latest)}</span>
            <p className="coach-reasoning">{displayedReasoning(latest)}</p>
          </div>
          {latest.provider !== "heuristic" && latest.source_reasoning ? (
            <div className="coach-reasoning-block coach-reasoning-block--public">
              <span>公开说明</span>
              <p className="coach-reasoning">{latest.reasoning}</p>
            </div>
          ) : null}
          {latest.fallback_used ? (
            <p className="fallback-reason">
              {fallbackReasonLabel(latest.fallback_reason)}
            </p>
          ) : null}
        </div>
      ) : (
        <span className="muted-state">
          {isFiltered ? "该玩家暂无决策记录" : "暂无电脑决策"}
        </span>
      )}
      <div className="coach-content coach-content--review">
        <div className="coach-action">
          <span>玩家复盘</span>
          <strong>
            {latestReview
              ? `${latestReview.score} 分 · ${latestReview.label}`
              : "暂无评价"}
          </strong>
        </div>
        {latestReview ? (
          <>
            <dl className="coach-metrics">
              <div>
                <dt>你的行动</dt>
                <dd>{actionWithAmount(latestReview.action, latestReview.amount)}</dd>
              </div>
              <div>
                <dt>建议行动</dt>
                <dd>
                  {latestReview.suggested_action
                    ? actionWithAmount(
                        latestReview.suggested_action,
                        latestReview.suggested_amount ?? 0,
                      )
                    : "无需调整"}
                </dd>
              </div>
              <div>
                <dt>评审源</dt>
                <dd>{providerLabel(latestReview.provider)}</dd>
              </div>
              <div>
                <dt>模型</dt>
                <dd>{modelLabel(latestReview.model)}</dd>
              </div>
            </dl>
            <div className="coach-reasoning-block">
              <span>即时评价</span>
              <p className="coach-reasoning">{latestReview.reasoning}</p>
            </div>
            {latestReview.fallback_used ? (
              <p className="fallback-reason">
                {fallbackReasonLabel(latestReview.fallback_reason)}
              </p>
            ) : null}
          </>
        ) : (
          <span className="muted-state">你行动后会显示即时复盘</span>
        )}
      </div>
    </section>
  );
}
