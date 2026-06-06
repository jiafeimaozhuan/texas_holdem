import type { CSSProperties } from "react";

const fixedSeatLayouts: Record<number, Array<[number, number]>> = {
  2: [
    [50, 86],
    [50, 14],
  ],
  3: [
    [50, 86],
    [12, 50],
    [88, 50],
  ],
  9: [
    [50, 89],
    [18, 82],
    [10, 55],
    [13, 28],
    [36, 13],
    [64, 13],
    [87, 28],
    [90, 55],
    [82, 82],
  ],
};

export function seatCoordinates(index: number, total: number): { x: number; y: number } {
  const fixedLayout = fixedSeatLayouts[total];
  if (fixedLayout) {
    const [x, y] = fixedLayout[index] ?? [50, 50];
    return { x, y };
  }

  if (total >= 4 && total <= 9) {
    const mirror = total - index;
    if (index > mirror) {
      const mirrored = seatCoordinates(mirror, total);
      return { x: 100 - mirrored.x, y: mirrored.y };
    }

    const angle = (2 * Math.PI * index) / total;
    return {
      x: Math.round(50 - 38 * Math.sin(angle)),
      y: Math.round(50 + 39 * Math.cos(angle)),
    };
  }

  return { x: 50, y: 50 };
}

export function seatPosition(index: number, total: number): CSSProperties {
  const { x, y } = seatCoordinates(index, total);

  return {
    "--seat-x": `${x}%`,
    "--seat-y": `${y}%`,
  } as CSSProperties;
}
