import type { BotStyle, CreateTableRequest } from "../types";

interface SettingsPanelProps {
  config: CreateTableRequest;
  disabled: boolean;
  onChange: (config: CreateTableRequest) => void;
  onCreateTable: () => Promise<void>;
}

const botStyles: BotStyle[] = [
  "tight_aggressive",
  "loose_aggressive",
  "conservative",
  "bluff_heavy",
  "gto_leaning",
];

function styleLabel(style: BotStyle): string {
  return style
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function normalizeBotStyles(styles: BotStyle[], botCount: number): BotStyle[] {
  const next = styles.slice(0, botCount);
  while (next.length < botCount) {
    next.push(botStyles[next.length % botStyles.length]);
  }
  return next;
}

export function SettingsPanel({
  config,
  disabled,
  onChange,
  onCreateTable,
}: SettingsPanelProps) {
  const seatCount = config.bot_count + 1;
  const normalizedStyles = normalizeBotStyles(config.bot_styles, config.bot_count);

  function updateNumber(key: keyof CreateTableRequest, value: number) {
    onChange({
      ...config,
      [key]: Math.max(1, Math.floor(value || 1)),
    });
  }

  function updateSeatCount(value: number) {
    const nextSeatCount = Math.min(9, Math.max(2, value));
    const botCount = nextSeatCount - 1;
    onChange({
      ...config,
      bot_count: botCount,
      human_seat: Math.min(config.human_seat, nextSeatCount - 1),
      bot_styles: normalizeBotStyles(config.bot_styles, botCount),
    });
  }

  function updateBotStyle(index: number, style: BotStyle) {
    const nextStyles = normalizeBotStyles(config.bot_styles, config.bot_count);
    nextStyles[index] = style;
    onChange({ ...config, bot_styles: nextStyles });
  }

  return (
    <section className="panel settings-panel" aria-label="Table settings">
      <div className="panel-heading">
        <div>
          <h2>Settings</h2>
          <span>Provider: heuristic/local</span>
        </div>
      </div>

      <div className="settings-grid">
        <label>
          <span>Seats</span>
          <input
            type="number"
            min={2}
            max={9}
            value={seatCount}
            disabled={disabled}
            onChange={(event) => updateSeatCount(Number(event.target.value))}
          />
        </label>
        <label>
          <span>Starting stack</span>
          <input
            type="number"
            min={1}
            value={config.starting_stack}
            disabled={disabled}
            onChange={(event) => updateNumber("starting_stack", Number(event.target.value))}
          />
        </label>
        <label>
          <span>Small blind</span>
          <input
            type="number"
            min={1}
            value={config.small_blind}
            disabled={disabled}
            onChange={(event) => updateNumber("small_blind", Number(event.target.value))}
          />
        </label>
        <label>
          <span>Big blind</span>
          <input
            type="number"
            min={1}
            value={config.big_blind}
            disabled={disabled}
            onChange={(event) => updateNumber("big_blind", Number(event.target.value))}
          />
        </label>
      </div>

      <div className="bot-style-list" aria-label="Bot style labels">
        {normalizedStyles.map((style, index) => (
          <label key={index}>
            <span>Bot {index + 1}</span>
            <select
              value={style}
              disabled={disabled}
              onChange={(event) => updateBotStyle(index, event.target.value as BotStyle)}
            >
              {botStyles.map((option) => (
                <option key={option} value={option}>
                  {styleLabel(option)}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <button type="button" className="wide-button" onClick={onCreateTable} disabled={disabled}>
        {disabled ? "Creating..." : "Create Table"}
      </button>
    </section>
  );
}
