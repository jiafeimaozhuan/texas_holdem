import type { ActionType, BotStyle } from "./types";

export function actionLabel(action?: string | null): string {
  const labels: Record<string, string> = {
    fold: "弃牌",
    check: "过牌",
    call: "跟注",
    bet: "下注",
    raise: "加注",
    all_in: "全下",
  };
  return action ? labels[action] ?? action : "行动";
}

export function actionWithAmount(action: ActionType | string, amount = 0): string {
  const label = actionLabel(action);
  if (amount <= 0 || action === "fold" || action === "check") {
    return label;
  }
  if (action === "raise") {
    return `${label}到 ${amount}`;
  }
  return `${label} ${amount}`;
}

export function streetLabel(street?: string | null): string {
  const labels: Record<string, string> = {
    waiting: "等待开局",
    preflop: "翻牌前",
    flop: "翻牌",
    turn: "转牌",
    river: "河牌",
    showdown: "摊牌",
    complete: "已结束",
  };
  return street ? labels[street] ?? street : "牌局";
}

export function styleLabel(style?: BotStyle | string | null): string {
  const labels: Record<string, string> = {
    tight_aggressive: "紧凶",
    loose_aggressive: "松凶",
    conservative: "保守",
    bluff_heavy: "诈唬型",
    gto_leaning: "GTO 倾向",
    human: "真人玩家",
  };
  return style ? labels[style] ?? style : "风格待定";
}

export function blindLabel(blind?: string | null): string {
  if (blind === "small_blind") {
    return "小盲";
  }
  if (blind === "big_blind") {
    return "大盲";
  }
  return blind ?? "";
}

export function seatLabel(seat?: number | null): string {
  return typeof seat === "number" ? `${seat + 1} 号位` : "牌桌";
}

export function socketStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    offline: "离线",
    connecting: "连接中",
    live: "已连接",
  };
  return labels[status] ?? status;
}

export function providerLabel(provider?: string | null): string {
  const labels: Record<string, string> = {
    heuristic: "本地规则",
    openai: "OpenAI",
    deepseek: "DeepSeek",
  };
  return provider ? labels[provider] ?? provider : "未配置";
}

export function modelLabel(model?: string | null): string {
  return model === "local" ? "本地" : model ?? "未配置";
}

export function providerStatusLabel(status?: string | null): string {
  if (!status) {
    return "未配置";
  }
  return status
    .split(", ")
    .map((part) => {
      if (part.startsWith("mixed: ")) {
        return `混合：${providerStatusLabel(part.slice("mixed: ".length))}`;
      }
      const [provider, model] = part.split("/");
      return model ? `${providerLabel(provider)}/${modelLabel(model)}` : providerLabel(part);
    })
    .join("，");
}

export function fallbackReasonLabel(reason?: string | null): string {
  if (!reason) {
    return "无回退原因";
  }
  if (reason.startsWith("primary_provider_error: ")) {
    return `主决策源错误：${reason.slice("primary_provider_error: ".length)}`;
  }
  if (reason === "illegal_primary_action") {
    return "主决策源返回了非法行动";
  }
  return reason;
}
