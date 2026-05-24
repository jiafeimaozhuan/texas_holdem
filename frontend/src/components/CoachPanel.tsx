import {
  actionWithAmount,
  fallbackReasonLabel,
  modelLabel,
  providerLabel,
  streetLabel,
  styleLabel,
} from "../labels";
import type { CoachEventView } from "../types";

interface CoachPanelProps {
  events: CoachEventView[];
}

function formatAction(event: CoachEventView): string {
  return actionWithAmount(event.action, event.amount);
}

export function CoachPanel({ events }: CoachPanelProps) {
  const latest = events.length > 0 ? events[events.length - 1] : undefined;

  return (
    <section className="panel coach-panel" aria-label="教练面板">
      <div className="panel-heading">
        <div>
          <h2>教练</h2>
          <span>
            {latest ? `第 ${latest.hand_number} 手 / ${streetLabel(latest.street)}` : "空闲"}
          </span>
        </div>
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

          <p className="coach-reasoning">{latest.reasoning}</p>
          {latest.fallback_used ? (
            <p className="fallback-reason">
              {fallbackReasonLabel(latest.fallback_reason)}
            </p>
          ) : null}
        </div>
      ) : (
        <span className="muted-state">暂无电脑决策</span>
      )}
    </section>
  );
}
