export type ActionType = "fold" | "check" | "call" | "bet" | "raise" | "all_in";

export type BotStyle =
  | "tight_aggressive"
  | "loose_aggressive"
  | "conservative"
  | "bluff_heavy"
  | "gto_leaning";

export interface CreateTableRequest {
  player_names?: string[] | null;
  human_name: string;
  bot_count: number;
  bot_styles: BotStyle[];
  starting_stack: number;
  small_blind: number;
  big_blind: number;
  human_seat: number;
  seed?: number | null;
}

export interface UpdateBotsRequest {
  bot_styles: BotStyle[];
}

export interface SubmitActionRequest {
  action: ActionType;
  amount: number;
}

export interface CardView {
  rank: string;
  suit: string;
  code: string;
}

export interface LegalActionView {
  action: ActionType;
  min_amount: number;
  max_amount: number;
}

export interface PlayerView {
  seat: number;
  name: string;
  stack: number;
  is_human: boolean;
  folded: boolean;
  all_in: boolean;
  street_bet: number;
  total_committed: number;
  hole_cards?: CardView[] | null;
}

export interface CoachEventView {
  type: "ai_decision";
  hand_number: number;
  street: string;
  seat: number;
  name: string;
  style: BotStyle;
  provider: string;
  model: string;
  action: ActionType;
  amount: number;
  confidence: number;
  reasoning: string;
  source_reasoning?: string | null;
  fallback_used: boolean;
  fallback_reason?: string | null;
}

export interface HumanReviewEventView {
  type: "human_review";
  hand_number: number;
  street: string;
  seat: number;
  name: string;
  action: ActionType;
  amount: number;
  score: number;
  label: string;
  reasoning: string;
  suggested_action?: ActionType | null;
  suggested_amount?: number | null;
  provider: string;
  model: string;
  fallback_used: boolean;
  fallback_reason?: string | null;
}

export interface HistoryEventView {
  type: string;
  hand_number?: number | null;
  dealer_seat?: number | null;
  street?: string | null;
  seat?: number | null;
  action?: string | null;
  amount?: number | null;
  blind?: string | null;
  cards?: string | null;
  board_count?: number | null;
  winners?: number[] | null;
  pot?: number | null;
  reason?: string | null;
  share?: number | null;
  remainder?: number | null;
  ranks?: Record<number, Record<string, unknown>> | null;
  name?: string | null;
  style?: BotStyle | null;
  provider?: string | null;
  model?: string | null;
  confidence?: number | null;
  reasoning?: string | null;
  source_reasoning?: string | null;
  fallback_used?: boolean | null;
  fallback_reason?: string | null;
  score?: number | null;
  label?: string | null;
  suggested_action?: string | null;
  suggested_amount?: number | null;
  [key: string]: unknown;
}

export interface TableStateResponse {
  table_id: string;
  hand_number: number;
  street: string;
  board: CardView[];
  pot: number;
  current_bet: number;
  min_raise: number;
  current_actor_seat?: number | null;
  dealer_seat: number;
  small_blind: number;
  big_blind: number;
  human_seat: number;
  players: PlayerView[];
  legal_actions: LegalActionView[];
  coach_events: CoachEventView[];
  human_review_events: HumanReviewEventView[];
  history_events: HistoryEventView[];
  ai_provider_status: string;
}

export interface StartHandResponse {
  table_id: string;
  state: TableStateResponse;
}
