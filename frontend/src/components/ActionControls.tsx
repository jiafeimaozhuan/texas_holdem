import { useEffect, useMemo, useState } from "react";
import { actionLabel, seatLabel } from "../labels";
import type { ActionType, LegalActionView, TableStateResponse } from "../types";

interface ActionControlsProps {
  state: TableStateResponse | null;
  isSubmitting: boolean;
  onSubmit: (action: ActionType, amount: number) => Promise<void>;
}

const rangedActions = new Set<ActionType>(["bet", "raise", "all_in"]);
const emptyLegalActions: LegalActionView[] = [];

function defaultAmount(action: LegalActionView): number {
  if (action.action === "fold" || action.action === "check") {
    return 0;
  }
  return action.min_amount;
}

function defaultAmountValue(action: LegalActionView): string {
  return String(defaultAmount(action));
}

function submitAmount(action: LegalActionView, amountValue: string): number {
  if (action.action === "fold" || action.action === "check") {
    return 0;
  }
  if (action.min_amount === action.max_amount) {
    return action.min_amount;
  }
  return Number(amountValue);
}

function validateAmount(action: LegalActionView, amountValue: string): string | null {
  if (action.action === "fold" || action.action === "check") {
    return null;
  }
  if (action.min_amount === action.max_amount) {
    return null;
  }

  const trimmed = amountValue.trim();
  if (!trimmed) {
    return "请输入金额";
  }
  if (!/^\d+$/.test(trimmed)) {
    return "金额必须是非负整数";
  }

  const amount = Number(trimmed);
  if (!Number.isSafeInteger(amount)) {
    return "金额过大，请重新输入";
  }
  if (amount < action.min_amount) {
    return `金额不能小于 ${action.min_amount}`;
  }
  if (amount > action.max_amount) {
    return `金额不能大于 ${action.max_amount}`;
  }
  return null;
}

export function ActionControls({ state, isSubmitting, onSubmit }: ActionControlsProps) {
  const [amounts, setAmounts] = useState<Record<ActionType, string>>({
    fold: "0",
    check: "0",
    call: "0",
    bet: "0",
    raise: "0",
    all_in: "0",
  });
  const [validationError, setValidationError] = useState<string | null>(null);

  const legalActions = state?.legal_actions ?? emptyLegalActions;
  const isHumanTurn = Boolean(
    state && state.current_actor_seat === state.human_seat && legalActions.length > 0,
  );

  useEffect(() => {
    setAmounts((current) => {
      const next = { ...current };
      let changed = false;
      for (const action of legalActions) {
        const amount = current[action.action] || defaultAmountValue(action);
        if (amount !== current[action.action]) {
          next[action.action] = amount;
          changed = true;
        }
      }
      return changed ? next : current;
    });
    setValidationError(null);
  }, [legalActions]);

  async function handleSubmit(legalAction: LegalActionView): Promise<void> {
    const amountValue = amounts[legalAction.action] ?? defaultAmountValue(legalAction);
    const error = validateAmount(legalAction, amountValue);
    if (error) {
      setValidationError(`${actionLabel(legalAction.action)}：${error}`);
      return;
    }
    setValidationError(null);
    await onSubmit(legalAction.action, submitAmount(legalAction, amountValue.trim()));
  }

  const status = useMemo(() => {
    if (!state) {
      return "尚未创建牌桌";
    }
    if (state.current_actor_seat == null) {
      return "手牌空闲";
    }
    const actor = state.players.find((player) => player.seat === state.current_actor_seat);
    return actor ? `轮到 ${actor.name} 行动` : `轮到${seatLabel(state.current_actor_seat)}行动`;
  }, [state]);

  return (
    <section className="panel action-panel" aria-label="行动控制">
      <div className="panel-heading">
        <div>
          <h2>行动</h2>
          <span>{status}</span>
        </div>
      </div>

      <div className="action-list">
        {validationError ? (
          <p className="action-error" role="alert">
            {validationError}
          </p>
        ) : null}
        {legalActions.length === 0 ? (
          <span className="muted-state">暂无可用行动</span>
        ) : (
          legalActions.map((legalAction) => {
            const hasAmountControl = rangedActions.has(legalAction.action);
            const isFixedAmount = legalAction.min_amount === legalAction.max_amount;
            const amount = amounts[legalAction.action] ?? defaultAmountValue(legalAction);

            return (
              <div className="action-row" key={legalAction.action}>
                <button
                  type="button"
                  onClick={() => void handleSubmit(legalAction)}
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
                    <span>金额</span>
                    <input
                      type="number"
                      min={legalAction.min_amount}
                      max={legalAction.max_amount}
                      value={amount}
                      inputMode="numeric"
                      aria-invalid={
                        validationError?.startsWith(actionLabel(legalAction.action)) ||
                        undefined
                      }
                      disabled={!isHumanTurn || isSubmitting}
                      readOnly={isFixedAmount}
                      onChange={(event) => {
                        if (isFixedAmount) {
                          return;
                        }
                        setValidationError(null);
                        setAmounts((current) => ({
                          ...current,
                          [legalAction.action]: event.target.value,
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
