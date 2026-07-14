"""An automatic Minesweeper solver built on the Minefield engine in minesweeper.py.

The solver never peeks at mine locations. It only uses information a human
player would have: revealed numbers, flag positions, and the total mine count.

It works in three tiers, escalating only when the previous tier is stuck:

1. Trivial rules      - if a number's remaining mines equal its hidden
                        neighbors, they are all mines; if a number is already
                        satisfied by flags, its other neighbors are safe.
2. Subset reduction   - if constraint A's cells are a subset of constraint
                        B's, subtracting A from B can create new certainties
                        (this cracks classic 1-2-1 / 1-2-2-1 patterns).
3. Enumeration        - enumerate every consistent mine layout for each
                        connected frontier component; cells that are mines in
                        every layout (or in none) are proven, not guessed.
4. Probability guess  - only when nothing on the board is provably safe,
                        reveal the cell with the lowest mine probability
                        (comparing against off-frontier cells too).

Run with:
    python autosweeper.py                     # watch one Beginner game (console)
    python autosweeper.py --gui               # watch the solver play in a window
    python autosweeper.py --gui -d Expert --delay 0.05
    python autosweeper.py -n 500 -d Intermediate   # batch stats, no board output
    python autosweeper.py --seed 42 --delay 0.3    # reproducible, slowed down
"""

from __future__ import annotations

import argparse
import itertools
import random
import time
import tkinter as tk
from collections import defaultdict, deque
from dataclasses import dataclass, field
from tkinter import ttk

from minesweeper import DIFFICULTIES, CellState, Coord, Minefield, MinesweeperApp


# Frontier components larger than this are not enumerated exhaustively;
# the solver falls back to a per-constraint density heuristic instead.
MAX_ENUMERATION_CELLS = 24


@dataclass(frozen=True)
class Constraint:
    """`mines` of the cells in `cells` are mines."""

    cells: frozenset[Coord]
    mines: int


@dataclass
class Move:
    action: str  # "reveal" or "flag"
    cell: Coord
    reason: str
    risk: float = 0.0  # estimated mine probability for guesses


@dataclass
class GameResult:
    won: bool
    moves: int = 0
    guesses: int = 0
    log: list[Move] = field(default_factory=list)


class AutoSweeper:
    def __init__(self, field_: Minefield) -> None:
        self.field = field_

    # ------------------------------------------------------------------
    # Board inspection helpers (public information only)
    # ------------------------------------------------------------------

    def _hidden_cells(self) -> list[Coord]:
        return [
            (row, column)
            for row in range(self.field.rows)
            for column in range(self.field.columns)
            if self.field.cells[row][column].state is CellState.HIDDEN
        ]

    def _flagged_cells(self) -> set[Coord]:
        return {
            (row, column)
            for row in range(self.field.rows)
            for column in range(self.field.columns)
            if self.field.cells[row][column].state is CellState.FLAGGED
        }

    def _constraints(self) -> list[Constraint]:
        """One constraint per revealed number that still has hidden neighbors."""
        constraints = []
        for row in range(self.field.rows):
            for column in range(self.field.columns):
                cell = self.field.cells[row][column]
                if cell.state is not CellState.REVEALED or cell.adjacent_mines == 0:
                    continue
                hidden = []
                flagged = 0
                for neighbor in self.field.neighbors(row, column):
                    state = self.field.cells[neighbor[0]][neighbor[1]].state
                    if state is CellState.HIDDEN:
                        hidden.append(neighbor)
                    elif state is CellState.FLAGGED:
                        flagged += 1
                if hidden:
                    constraints.append(
                        Constraint(frozenset(hidden), cell.adjacent_mines - flagged)
                    )
        return constraints

    # ------------------------------------------------------------------
    # Tier 1 + 2: logical deduction
    # ------------------------------------------------------------------

    def _deduce(self) -> list[Move]:
        """Find all certain moves from the current position."""
        constraints = self._constraints()
        safe: set[Coord] = set()
        mines: set[Coord] = set()

        for constraint in constraints:
            if constraint.mines == 0:
                safe.update(constraint.cells)
            elif constraint.mines == len(constraint.cells):
                mines.update(constraint.cells)

        # Subset reduction: B - A must contain B.mines - A.mines mines.
        for a, b in itertools.permutations(constraints, 2):
            if a.cells < b.cells:
                difference = b.cells - a.cells
                remaining = b.mines - a.mines
                if remaining == 0:
                    safe.update(difference)
                elif remaining == len(difference):
                    mines.update(difference)

        # Global mine-count constraint: if every unflagged mine is accounted
        # for, everything else is safe; if hidden cells == remaining mines,
        # they are all mines.
        hidden = set(self._hidden_cells())
        mines_left = self.field.mine_count - len(self._flagged_cells())
        if mines_left == len(mines) and mines:
            safe.update(hidden - mines)
        if mines_left == len(hidden):
            mines.update(hidden)

        moves = [Move("flag", cell, "deduced mine") for cell in sorted(mines)]
        moves += [Move("reveal", cell, "deduced safe") for cell in sorted(safe - mines)]
        return moves

    # ------------------------------------------------------------------
    # Tier 3: probability-based guessing
    # ------------------------------------------------------------------

    def _components(
        self, constraints: list[Constraint]
    ) -> list[tuple[list[Coord], list[Constraint]]]:
        """Group frontier cells and constraints into connected components."""
        cell_to_constraints: dict[Coord, list[int]] = defaultdict(list)
        for index, constraint in enumerate(constraints):
            for cell in constraint.cells:
                cell_to_constraints[cell].append(index)

        seen_cells: set[Coord] = set()
        components = []
        for start in cell_to_constraints:
            if start in seen_cells:
                continue
            component_cells: set[Coord] = set()
            component_constraints: set[int] = set()
            pending = [start]
            while pending:
                cell = pending.pop()
                if cell in component_cells:
                    continue
                component_cells.add(cell)
                for index in cell_to_constraints[cell]:
                    if index not in component_constraints:
                        component_constraints.add(index)
                        pending.extend(constraints[index].cells)
            seen_cells.update(component_cells)
            components.append(
                (sorted(component_cells), [constraints[i] for i in component_constraints])
            )
        return components

    def _enumerate_component(
        self, cells: list[Coord], constraints: list[Constraint], mines_cap: int
    ) -> dict[Coord, float] | None:
        """Exact per-cell mine probability via backtracking enumeration.

        Returns None when the component is too large to enumerate.
        """
        if len(cells) > MAX_ENUMERATION_CELLS:
            return None

        cell_index = {cell: i for i, cell in enumerate(cells)}
        # For pruning, order cells so that constraint members are adjacent.
        ordered: list[Coord] = []
        for constraint in constraints:
            for cell in sorted(constraint.cells):
                if cell not in ordered:
                    ordered.append(cell)
        for cell in cells:
            if cell not in ordered:
                ordered.append(cell)

        constraint_data = [
            ([cell_index[c] for c in constraint.cells], constraint.mines)
            for constraint in constraints
        ]

        assignment = [False] * len(cells)
        mine_solution_counts = [0] * len(cells)
        solution_count = 0

        def satisfiable(position: int) -> bool:
            """Check no constraint is already violated given cells[:position] decided."""
            decided = {cell_index[ordered[i]] for i in range(position)}
            for members, required in constraint_data:
                assigned = sum(assignment[m] for m in members if m in decided)
                undecided = sum(1 for m in members if m not in decided)
                if assigned > required or assigned + undecided < required:
                    return False
            return True

        def backtrack(position: int, mines_used: int) -> None:
            nonlocal solution_count
            if mines_used > mines_cap:
                return
            if position == len(ordered):
                solution_count += 1
                for i, is_mine in enumerate(assignment):
                    if is_mine:
                        mine_solution_counts[i] += 1
                return
            index = cell_index[ordered[position]]
            for value in (False, True):
                assignment[index] = value
                if satisfiable(position + 1):
                    backtrack(position + 1, mines_used + value)
            assignment[index] = False

        backtrack(0, 0)
        if solution_count == 0:
            return None
        return {
            cell: mine_solution_counts[cell_index[cell]] / solution_count
            for cell in cells
        }

    def _probabilities(self) -> tuple[dict[Coord, float], set[Coord]]:
        """Per-cell mine probabilities, plus which cells have exact values.

        Cells in the exact set were fully enumerated: a probability of 0.0 or
        1.0 there is a proof, not an estimate.
        """
        constraints = self._constraints()
        hidden = set(self._hidden_cells())
        mines_left = self.field.mine_count - len(self._flagged_cells())

        probabilities: dict[Coord, float] = {}
        exact_cells: set[Coord] = set()
        frontier: set[Coord] = set()
        expected_frontier_mines = 0.0

        for cells, component_constraints in self._components(constraints):
            frontier.update(cells)
            exact = self._enumerate_component(cells, component_constraints, mines_left)
            if exact is not None:
                probabilities.update(exact)
                exact_cells.update(cells)
                expected_frontier_mines += sum(exact.values())
            else:
                # Fallback: each cell gets the max density of its constraints.
                for cell in cells:
                    density = max(
                        constraint.mines / len(constraint.cells)
                        for constraint in component_constraints
                        if cell in constraint.cells
                    )
                    probabilities[cell] = density
                    expected_frontier_mines += density

        off_frontier = hidden - frontier
        if off_frontier:
            remaining = max(mines_left - expected_frontier_mines, 0.0)
            density = min(remaining / len(off_frontier), 1.0)
            for cell in off_frontier:
                probabilities[cell] = density

        return probabilities, exact_cells

    def _enumeration_certainties(
        self, probabilities: dict[Coord, float], exact_cells: set[Coord]
    ) -> list[Move]:
        """Turn proven 0%/100% enumeration results into certain moves."""
        moves = []
        for cell in sorted(exact_cells):
            if probabilities[cell] == 1.0:
                moves.append(Move("flag", cell, "proven mine (enumeration)"))
            elif probabilities[cell] == 0.0:
                moves.append(Move("reveal", cell, "proven safe (enumeration)"))
        return moves

    def _guess(self, probabilities: dict[Coord, float]) -> Move:
        """Pick the hidden cell with the lowest estimated mine probability."""

        # Break probability ties by preferring corners/edges: fewer neighbors
        # means a reveal there is more likely to open up the board.
        def sort_key(cell: Coord) -> tuple[float, int, Coord]:
            neighbor_count = sum(1 for _ in self.field.neighbors(*cell))
            return (round(probabilities[cell], 6), neighbor_count, cell)

        best = min(probabilities, key=sort_key)
        return Move(
            "reveal",
            best,
            f"guess ({probabilities[best]:.0%} mine chance)",
            risk=probabilities[best],
        )

    # ------------------------------------------------------------------
    # Driving the game
    # ------------------------------------------------------------------

    def next_moves(self) -> tuple[list[Move], bool]:
        """Return the next batch of moves and whether any was a guess."""
        if not self.field.mines_placed:
            # First click: the engine guarantees it and its neighbors are safe,
            # so open near the center for maximum expansion.
            center = (self.field.rows // 2, self.field.columns // 2)
            return [Move("reveal", center, "opening move")], False

        deduced = self._deduce()
        if deduced:
            return deduced, False

        # Cheap rules are exhausted; try full enumeration before guessing.
        # Anything proven 0% or 100% is still a deduction, not a guess.
        probabilities, exact_cells = self._probabilities()
        certain = self._enumeration_certainties(probabilities, exact_cells)
        if certain:
            return certain, False
        return [self._guess(probabilities)], True

    def play(
        self, on_move: "callable | None" = None, max_moves: int = 100_000
    ) -> GameResult:
        result = GameResult(won=False)
        while not self.field.game_over and result.moves < max_moves:
            moves, guessed = self.next_moves()
            result.guesses += guessed
            for move in moves:
                if self.field.game_over:
                    break
                if move.action == "flag":
                    row, column = move.cell
                    if self.field.cells[row][column].state is CellState.HIDDEN:
                        self.field.toggle_flag(row, column)
                else:
                    self.field.reveal(*move.cell)
                result.moves += 1
                result.log.append(move)
                if on_move is not None:
                    on_move(move)
        result.won = self.field.won
        return result


# ----------------------------------------------------------------------
# GUI watch mode
# ----------------------------------------------------------------------


class SolverViewer:
    """A tkinter window that shows the solver playing, one move per tick."""

    HIGHLIGHT_REVEAL = "#fff176"
    HIGHLIGHT_FLAG = "#ffb74d"

    def __init__(
        self,
        root: tk.Tk,
        rows: int,
        columns: int,
        mines: int,
        rng: random.Random,
        delay_ms: int,
    ) -> None:
        self.root = root
        self.rows = rows
        self.columns = columns
        self.mines = mines
        self.rng = rng
        self.delay_ms = delay_ms
        self.root.title("AutoSweeper")
        self.root.resizable(False, False)

        self.status_text = tk.StringVar()
        self.counter_text = tk.StringVar()
        self.paused = False
        self.tick_job: str | None = None

        controls = ttk.Frame(root, padding=10)
        controls.grid(row=0, column=0, sticky="ew")
        self.pause_button = ttk.Button(controls, text="Pause", command=self._toggle_pause)
        self.pause_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(controls, text="New Game", command=self._new_game).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(controls, text="Random Seed", command=self._new_random_game).grid(
            row=0, column=2, padx=(0, 12)
        )
        ttk.Label(controls, textvariable=self.counter_text).grid(row=0, column=3)

        self.board_frame = ttk.Frame(root, padding=(10, 0, 10, 8))
        self.board_frame.grid(row=1, column=0)
        ttk.Label(root, textvariable=self.status_text, anchor="center").grid(
            row=2, column=0, sticky="ew", padx=10, pady=(0, 8)
        )

        self.labels: list[list[tk.Label]] = []
        label_width = 2 if columns <= 16 else 1
        for row in range(rows):
            label_row: list[tk.Label] = []
            for column in range(columns):
                label = tk.Label(
                    self.board_frame,
                    text="",
                    width=label_width,
                    height=1,
                    font=("Segoe UI", 10, "bold"),
                    bg=MinesweeperApp.HIDDEN_COLOR,
                    relief=tk.RAISED,
                    borderwidth=2,
                )
                label.grid(row=row, column=column, sticky="nsew")
                label_row.append(label)
            self.labels.append(label_row)

        self._new_game()

    def _new_game(self) -> None:
        self._cancel_tick()
        self.field = Minefield(self.rows, self.columns, self.mines, rng=self.rng)
        self.solver = AutoSweeper(self.field)
        self.pending: deque[Move] = deque()
        self.move_count = 0
        self.guess_count = 0
        self.paused = False
        self.pause_button.configure(text="Pause")
        self.status_text.set("Solving...")
        self._refresh_all()
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        self._cancel_tick()
        self.tick_job = self.root.after(self.delay_ms, self._tick)

    def _cancel_tick(self) -> None:
        if self.tick_job is not None:
            self.root.after_cancel(self.tick_job)
            self.tick_job = None

    def _new_random_game(self) -> None:
        self.rng = random.Random()
        self._new_game()

    def _toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_button.configure(text="Resume" if self.paused else "Pause")
        if self.paused:
            self._cancel_tick()
        else:
            self._schedule_tick()

    def _tick(self) -> None:
        self.tick_job = None
        if self.paused or self.field.game_over:
            return

        if not self.pending:
            moves, guessed = self.solver.next_moves()
            self.guess_count += guessed
            self.pending.extend(moves)

        move = self.pending.popleft()
        row, column = move.cell
        if move.action == "flag":
            if self.field.cells[row][column].state is CellState.HIDDEN:
                self.field.toggle_flag(row, column)
        else:
            self.field.reveal(row, column)
        self.move_count += 1

        self._refresh_all()
        highlight = (
            self.HIGHLIGHT_FLAG if move.action == "flag" else self.HIGHLIGHT_REVEAL
        )
        self.labels[row][column].configure(bg=highlight)
        self.status_text.set(f"{move.action} {move.cell} — {move.reason}")
        self.counter_text.set(
            f"Moves: {self.move_count}   Guesses: {self.guess_count}"
        )

        if self.field.game_over:
            self._finish()
        else:
            self._schedule_tick()

    def _finish(self) -> None:
        if self.field.won:
            self.status_text.set(
                f"Solved in {self.move_count} moves ({self.guess_count} guesses)!"
            )
        else:
            # Show every mine so the losing guess is visible in context.
            for row in self.field.cells:
                for cell in row:
                    if cell.is_mine:
                        cell.state = CellState.REVEALED
            self._refresh_all()
            self.status_text.set(
                f"Hit a mine after {self.move_count} moves "
                f"({self.guess_count} guesses). Click New Game to retry."
            )

    def _refresh_all(self) -> None:
        for row in range(self.rows):
            for column in range(self.columns):
                cell = self.field.cells[row][column]
                label = self.labels[row][column]
                if cell.state is CellState.FLAGGED:
                    label.configure(
                        text="⚑",
                        fg="#c62828",
                        bg=MinesweeperApp.HIDDEN_COLOR,
                        relief=tk.RAISED,
                    )
                elif cell.state is CellState.HIDDEN:
                    label.configure(
                        text="",
                        fg="black",
                        bg=MinesweeperApp.HIDDEN_COLOR,
                        relief=tk.RAISED,
                    )
                elif cell.is_mine:
                    label.configure(text="✹", fg="white", bg="#d32f2f", relief=tk.SUNKEN)
                else:
                    number = cell.adjacent_mines
                    label.configure(
                        text=str(number) if number else "",
                        fg=MinesweeperApp.NUMBER_COLORS.get(number, "black"),
                        bg=MinesweeperApp.REVEALED_COLOR,
                        relief=tk.SUNKEN,
                    )


def run_gui(rows: int, columns: int, mines: int, rng: random.Random, delay: float) -> None:
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    delay_ms = max(int(delay * 1000), 1) if delay > 0 else 150
    SolverViewer(root, rows, columns, mines, rng, delay_ms)
    root.mainloop()


# ----------------------------------------------------------------------
# Console rendering and CLI
# ----------------------------------------------------------------------


def render(field_: Minefield) -> str:
    symbols = []
    header = "    " + " ".join(f"{c:>2}" for c in range(field_.columns))
    symbols.append(header)
    for row in range(field_.rows):
        line = [f"{row:>3} "]
        for column in range(field_.columns):
            cell = field_.cells[row][column]
            if cell.state is CellState.FLAGGED:
                glyph = "F"
            elif cell.state is CellState.HIDDEN:
                glyph = "."
            elif cell.is_mine:
                glyph = "*"
            elif cell.adjacent_mines:
                glyph = str(cell.adjacent_mines)
            else:
                glyph = " "
            line.append(f"{glyph:>2} ")
        symbols.append("".join(line).rstrip())
    return "\n".join(symbols)


def play_one_verbose(rows: int, columns: int, mines: int, rng: random.Random, delay: float) -> GameResult:
    field_ = Minefield(rows, columns, mines, rng=rng)
    solver = AutoSweeper(field_)

    def on_move(move: Move) -> None:
        print(f"{move.action:>6} {move.cell}  [{move.reason}]")
        if delay > 0:
            print(render(field_))
            print()
            time.sleep(delay)

    result = solver.play(on_move=on_move)
    print()
    print(render(field_))
    verdict = "WON" if result.won else "LOST"
    print(
        f"\n{verdict} in {result.moves} moves "
        f"({result.guesses} guess{'es' if result.guesses != 1 else ''})."
    )
    return result


def run_batch(rows: int, columns: int, mines: int, games: int, rng: random.Random) -> None:
    wins = 0
    total_guesses = 0
    started = time.perf_counter()
    for game in range(1, games + 1):
        field_ = Minefield(rows, columns, mines, rng=rng)
        result = AutoSweeper(field_).play()
        wins += result.won
        total_guesses += result.guesses
        if game % 50 == 0 or game == games:
            print(f"  {game}/{games} games, {wins} wins ({wins / game:.1%})")
    elapsed = time.perf_counter() - started
    print(
        f"\nWin rate: {wins}/{games} ({wins / games:.1%})  "
        f"avg guesses/game: {total_guesses / games:.2f}  "
        f"({elapsed:.1f}s total)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Automatic Minesweeper solver.")
    parser.add_argument(
        "-d",
        "--difficulty",
        choices=list(DIFFICULTIES),
        default="Beginner",
        help="board preset (default: Beginner)",
    )
    parser.add_argument(
        "-n",
        "--games",
        type=int,
        default=1,
        help="number of games; more than 1 switches to batch stats mode",
    )
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="seconds between moves (GUI default: 0.15; console default: no pause)",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="watch the solver play in a window instead of the console",
    )
    args = parser.parse_args()

    rows, columns, mines = DIFFICULTIES[args.difficulty]
    rng = random.Random(args.seed)

    if args.gui:
        run_gui(rows, columns, mines, rng, args.delay)
    elif args.games > 1:
        run_batch(rows, columns, mines, args.games, rng)
    else:
        play_one_verbose(rows, columns, mines, rng, args.delay)


if __name__ == "__main__":
    main()
