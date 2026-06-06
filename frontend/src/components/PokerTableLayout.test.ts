import { seatCoordinates } from "./PokerTableLayout";

function assertCoordinates(
  actual: { x: number; y: number },
  expected: { x: number; y: number },
) {
  if (actual.x !== expected.x || actual.y !== expected.y) {
    throw new Error(
      `expected (${expected.x}, ${expected.y}), got (${actual.x}, ${actual.y})`,
    );
  }
}

function assertSeparated(
  first: { x: number; y: number },
  second: { x: number; y: number },
  label: string,
) {
  const xDistance = Math.abs(first.x - second.x);
  const yDistance = Math.abs(first.y - second.y);
  if (xDistance < 23 && yDistance < 23) {
    throw new Error(
      `expected ${label} to be separated, got dx=${xDistance}, dy=${yDistance}`,
    );
  }
}

assertCoordinates(seatCoordinates(0, 4), { x: 50, y: 89 });
assertCoordinates(seatCoordinates(1, 4), { x: 12, y: 50 });
assertCoordinates(seatCoordinates(2, 4), { x: 50, y: 11 });
assertCoordinates(seatCoordinates(3, 4), { x: 88, y: 50 });

assertCoordinates(seatCoordinates(0, 8), { x: 50, y: 89 });
assertCoordinates(seatCoordinates(1, 8), { x: 23, y: 78 });
assertCoordinates(seatCoordinates(2, 8), { x: 12, y: 50 });
assertCoordinates(seatCoordinates(3, 8), { x: 23, y: 22 });
assertCoordinates(seatCoordinates(4, 8), { x: 50, y: 11 });
assertCoordinates(seatCoordinates(5, 8), { x: 77, y: 22 });
assertCoordinates(seatCoordinates(6, 8), { x: 88, y: 50 });
assertCoordinates(seatCoordinates(7, 8), { x: 77, y: 78 });

assertCoordinates(seatCoordinates(0, 9), { x: 50, y: 89 });
assertCoordinates(seatCoordinates(1, 9), { x: 18, y: 82 });
assertCoordinates(seatCoordinates(2, 9), { x: 10, y: 55 });
assertCoordinates(seatCoordinates(3, 9), { x: 13, y: 28 });
assertCoordinates(seatCoordinates(4, 9), { x: 36, y: 13 });
assertCoordinates(seatCoordinates(5, 9), { x: 64, y: 13 });
assertCoordinates(seatCoordinates(6, 9), { x: 87, y: 28 });
assertCoordinates(seatCoordinates(7, 9), { x: 90, y: 55 });
assertCoordinates(seatCoordinates(8, 9), { x: 82, y: 82 });

for (let index = 0; index < 9; index += 1) {
  assertSeparated(
    seatCoordinates(index, 9),
    seatCoordinates((index + 1) % 9, 9),
    `9-seat positions ${index + 1} and ${((index + 1) % 9) + 1}`,
  );
}

for (let total = 4; total <= 9; total += 1) {
  for (let index = 1; index < total; index += 1) {
    const mirror = total - index;
    if (index >= mirror) {
      continue;
    }

    const left = seatCoordinates(index, total);
    const right = seatCoordinates(mirror, total);
    if (left.x + right.x !== 100 || left.y !== right.y) {
      throw new Error(
        `expected ${total}-seat table positions ${index + 1} and ${
          mirror + 1
        } to mirror, got (${left.x}, ${left.y}) and (${right.x}, ${right.y})`,
      );
    }
  }
}
