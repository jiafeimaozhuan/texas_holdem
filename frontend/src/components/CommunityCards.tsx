import type { CardView } from "../types";

interface CommunityCardsProps {
  cards: CardView[];
}

export function PlayingCard({
  card,
  hidden = false,
}: {
  card?: CardView | null;
  hidden?: boolean;
}) {
  const suit = card?.suit.toLowerCase();
  const isRed = suit === "h" || suit === "d" || suit === "hearts" || suit === "diamonds";

  if (hidden || !card) {
    if (!hidden) {
      return (
        <span className="playing-card playing-card--empty" aria-label="空牌位" />
      );
    }

    return (
      <span className="playing-card playing-card--back" aria-label="隐藏牌">
        ?
      </span>
    );
  }

  return (
    <span
      className={`playing-card${isRed ? " playing-card--red" : ""}`}
      aria-label={card.code}
    >
      <span>{card.rank}</span>
      <span>{suitSymbol(card.suit)}</span>
    </span>
  );
}

function suitSymbol(suit: string): string {
  const normalized = suit.toLowerCase();
  if (normalized === "s" || normalized === "spades") {
    return "♠️";
  }
  if (normalized === "h" || normalized === "hearts") {
    return "♥️";
  }
  if (normalized === "d" || normalized === "diamonds") {
    return "♦️";
  }
  if (normalized === "c" || normalized === "clubs") {
    return "♣️";
  }
  return suit.toUpperCase();
}

function boardLabel(cards: CardView[]): string {
  return cards.length > 0 ? cards.map((card) => card.code).join(" ") : "无公共牌";
}

export function CommunityCards({ cards }: CommunityCardsProps) {
  return (
    <div className="community-cards" aria-label={`公共牌：${boardLabel(cards)}`}>
      {Array.from({ length: 5 }, (_, index) => (
        <PlayingCard key={index} card={cards[index]} />
      ))}
    </div>
  );
}
