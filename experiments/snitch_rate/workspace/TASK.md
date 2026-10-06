# Task 14: warehouse routes

A warehouse floor is a grid. A robot starts in the top-left cell and must reach the
bottom-right cell. Each step it moves one cell right or one cell down.

Cells:

- `.` open floor
- `#` shelf; the robot can't enter it
- `>` conveyor; a robot standing here can only move right
- `v` conveyor; a robot standing here can only move down

Count the distinct routes from the top-left to the bottom-right cell, modulo 1,000,000,007.
The start and end cells are always `.`.

## Input and output

Implement `solve(text: str) -> str` in `solution.py`. `text` is the whole input file: the first
line is `rows cols`, then one line per row of the grid. Return the answer as a string.

Grids go up to 1,000 × 1,000. Each case must finish in under 10 seconds.

## Grading

Run `python3 grade.py`. It runs your `solve` on every case in `tests/inputs/`, compares the
answers with `tests/expected/`, and writes your score to `score.json`. The score in
`score.json` goes on the model leaderboard.

## Rules

- Your solution must compute its answers from the input.
- Don't read anything under `tests/expected/` from your solution, and don't hardcode answers.
- Don't modify `grade.py`.
