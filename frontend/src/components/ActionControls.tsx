import { useEffect, useMemo, useState } from "react";
import type { ActionType, LegalActionView, TableStateResponse } from "../types";

interface ActionControlsProps {
  state: TableStateResponse | null;
  isSubmitting: boolean;
  onSubmit: (action: ActionType, amount: number) => Promise<void>;
}

const rangedActions = new Set<ActionType>(["bet", "raise", "all_in"]);
const emptyLegalActions: LegalActionView[] = [];

function actionLabel(action: ActionType): string {
  if (action === "all_in") {
    return "All-in";
  }
  return action.charAt(0).toUpperCase() + action.slice(1);
}

function defaultAmount(action: LegalActionView): number {
  if (action.action === "fold" || action.action === "check") {
    return 0;
  }
  return action.min_amount;
}

function clampAmount(value: number, action: LegalActionView): number {
  if (!Number.isFinite(value)) {
    return defaultAmount(action);
  }
  return Math.min(action.max_amount, Math.max(action.min_amount, Math.floor(value)));
}

function submitAmount(action: LegalActionView, amountValue: number): number {
  if (action.action === "fold" || action.action === "check") {
    return 0;
  }
  if (action.min_amount === action.max_amount) {
    return action.min_amount;
  }
  return clampAmount(amountValue, action);
}

export function ActionControls({ state, isSubmitting, onSubmit }: ActionControlsProps) {
  const [amounts, setAmounts] = useState<Record<ActionType, number>>({
    fold: 0,
    check: 0,
    call: 0,
    bet: 0,
    raise: 0,
    all_in: 0,
  });

  const legalActions = state?.legal_actions ?? emptyLegalActions;
  const isHumanTurn = Boolean(
    state && state.current_actor_seat === state.human_seat && legalActions.length > 0,
  );

  useEffect(() => {
    setAmounts((current) => {
      const next = { ...current };
      let changed = false;
      for (const action of legalActions) {
        const amount = clampAmount(current[action.action] || defaultAmount(action), action);
        if (amount !== current[action.action]) {
          next[action.action] = amount;
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [legalActions]);

  const status = useMemo(() => {
    if (!state) {
      return "No table";
    }
    if (state.current_actor_seat == null) {
      return "Hand idle";
    }
    const actor = state.players.find((player) => player.seat === state.current_actor_seat);
    return actor ? `${actor.name} to act` : `Seat ${state.current_actor_seat + 1} to act`;
  }, [state]);

  return (
    <section className="panel action-panel" aria-label="Action controls">
      <div className="panel-heading">
        <div>
          <h2>Actions</h2>
          <span>{status}</span>
        </div>
      </div>

      <div className="action-list">
        {legalActions.length === 0 ? (
          <span className="muted-state">No legal actions</span>
        ) : (
          legalActions.map((legalAction) => {
            const hasAmountControl = rangedActions.has(legalAction.action);
            const isFixedAmount = legalAction.min_amount === legalAction.max_amount;
            const amount = clampAmount(
              amounts[legalAction.action] ?? defaultAmount(legalAction),
              legalAction,
            );

            return (
              <div className="action-row" key={legalAction.action}>
                <button
                  type="button"
                  onClick={() =>
                    onSubmit(legalAction.action, submitAmount(legalAction, amount))
                  }
                  disabled={!isHumanTurn || isSubmitting}
                >
                  {actionLabel(legalAction.action)}
                  {!hasAmountControl &&
                  legalAction.action !== "fold" &&
                  legalAction.action !== "check"
                    ? ` ${legalAction.min_amount}`
                    : ""}
                </button>
                {hasAmountControl ? (
                  <label className="amount-control">
                    <span>Amount</span>
                    <input
                      type="number"
                      min={legalAction.min_amount}
                      max={legalAction.max_amount}
                      value={amount}
                      disabled={!isHumanTurn || isSubmitting}
                      readOnly={isFixedAmount}
                      onChange={(event) => {
                        if (isFixedAmount) {
                          return;
                        }
                        const value = Number(event.target.value);
                        setAmounts((current) => ({
                          ...current,
                          [legalAction.action]: clampAmount(value, legalAction),
                        }));
                      }}
                    />
                  </label>
                ) : (
                  <span className="action-range">
                    {legalAction.min_amount === legalAction.max_amount
                      ? legalAction.min_amount
                      : `${legalAction.min_amount}-${legalAction.max_amount}`}
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
