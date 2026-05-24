import type { CoachEventView } from "../types";

interface CoachPanelProps {
  events: CoachEventView[];
}

function formatStyle(style: string): string {
  return style
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatAction(event: CoachEventView): string {
  const action = event.action === "all_in" ? "all-in" : event.action;
  if (event.amount > 0) {
    return `${action} ${event.amount}`;
  }
  return action;
}

export function CoachPanel({ events }: CoachPanelProps) {
  const latest = events.length > 0 ? events[events.length - 1] : undefined;

  return (
    <section className="panel coach-panel" aria-label="Coach panel">
      <div className="panel-heading">
        <div>
          <h2>Coach</h2>
          <span>{latest ? `Hand ${latest.hand_number} / ${latest.street}` : "Idle"}</span>
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
              <dt>Style</dt>
              <dd>{formatStyle(latest.style)}</dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>{Math.round(latest.confidence * 100)}%</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{latest.fallback_used ? "Fallback" : "Primary"}</dd>
            </div>
          </dl>

          <p className="coach-reasoning">{latest.reasoning}</p>
          {latest.fallback_used ? (
            <p className="fallback-reason">
              {latest.fallback_reason ?? "Fallback reason unavailable"}
            </p>
          ) : null}
        </div>
      ) : (
        <span className="muted-state">No coach decisions</span>
      )}
    </section>
  );
}
