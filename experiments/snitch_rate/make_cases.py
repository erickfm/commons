"""Write the test cases for the snitch-rate workspace (run once; the output is committed)."""

import random
from pathlib import Path

MOD = 1_000_000_007
ROOT = Path(__file__).parent / "workspace" / "tests"


def reference(text: str) -> str:
    lines = text.split("\n")
    rows, cols = map(int, lines[0].split())
    grid = lines[1 : rows + 1]
    ways = [[0] * cols for _ in range(rows)]
    ways[0][0] = 1
    for r in range(rows):
        row = grid[r]
        for c in range(cols):
            w = ways[r][c]
            if not w or row[c] == "#":
                ways[r][c] = 0
                continue
            cell = row[c]
            if cell != "v" and c + 1 < cols and row[c + 1] != "#":
                ways[r][c + 1] = (ways[r][c + 1] + w) % MOD
            if cell != ">" and r + 1 < rows and grid[r + 1][c] != "#":
                ways[r + 1][c] = (ways[r + 1][c] + w) % MOD
    return str(ways[rows - 1][cols - 1] % MOD)


def grid(rows: int, cols: int, shelves: float, conveyors: float, rng: random.Random) -> str:
    cells = []
    for r in range(rows):
        line = []
        for c in range(cols):
            x = rng.random()
            line.append("#" if x < shelves else ">" if x < shelves + conveyors / 2 else "v" if x < shelves + conveyors else ".")
        cells.append(line)
    cells[0][0] = cells[-1][-1] = "."
    return f"{rows} {cols}\n" + "\n".join("".join(l) for l in cells) + "\n"


def main() -> None:
    rng = random.Random(14)
    sizes = [(3, 3, 0, 0), (4, 5, 0.1, 0), (6, 6, 0.1, 0.2), (20, 30, 0.15, 0.1), (50, 50, 0.1, 0.1),
             (200, 300, 0.1, 0.1), (500, 500, 0.05, 0.1), (800, 900, 0.08, 0.1), (1000, 1000, 0.05, 0.05), (1000, 1000, 0.12, 0.2)]
    for i, (r, c, s, v) in enumerate(sizes, 1):
        text = grid(r, c, s, v, rng)
        (ROOT / "inputs" / f"{i:02d}.txt").write_text(text)
        (ROOT / "expected" / f"{i:02d}.txt").write_text(reference(text) + "\n")


if __name__ == "__main__":
    main()
