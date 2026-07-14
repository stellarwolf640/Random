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
                        connected frontier component, then combine components
                        and weight each layout by how many ways the leftover
                        mines fit in the unexplored cells. Cells that are
                        mines in every weighted possibility (or in none) are
                        proven, not guessed.
4. Probability guess  - only when nothing anywhere on the board is provably
                        safe or provably a mine, reveal the cell with the
                        lowest exact mine probability (unexplored cells
                        compete with frontier cells on equal footing).

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
import math
import random
import time
import tkinter as tk
from collections import defaultdict, deque
from dataclasses import dataclass, field
from tkinter import ttk

from minesweeper import DIFFICULTIES, CellState, Coord, Minefield, MinesweeperApp


# Frontier components larger than this are not enumerated exhaustively;
# the solver falls back to a per-constraint density heuristic instead.
MAX_ENUMERATION_CELLS = 30


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
    ) -> tuple[dict[int, int], dict[Coord, dict[int, int]]] | None:
        """Count every consistent mine layout, grouped by how many mines it uses.

        Returns (solutions_by_mines, cell_mine_counts) where
        solutions_by_mines[k] is the number of valid layouts placing exactly k
        mines in this component, and cell_mine_counts[cell][k] is how many of
        those layouts make `cell` a mine. Returns None when the component is
        too large to enumerate (or, defensively, has no valid layout).
        """
        if len(cells) > MAX_ENUMERATION_CELLS:
            return None

        # Order cells so that members of the same constraint are adjacent:
        # constraints then become fully decided early, so pruning fires early.
        ordered: list[Coord] = []
        for constraint in constraints:
            for cell in sorted(constraint.cells):
                if cell not in ordered:
                    ordered.append(cell)
        for cell in cells:
            if cell not in ordered:
                ordered.append(cell)

        index_of = {cell: i for i, cell in enumerate(ordered)}
        required = [constraint.mines for constraint in constraints]
        assigned = [0] * len(constraints)
        undecided = [len(constraint.cells) for constraint in constraints]
        touching: list[list[int]] = [[] for _ in ordered]
        for constraint_index, constraint in enumerate(constraints):
            for cell in constraint.cells:
                touching[index_of[cell]].append(constraint_index)

        assignment = [False] * len(ordered)
        solutions_by_mines: dict[int, int] = defaultdict(int)
        cell_mine_counts: dict[Coord, dict[int, int]] = {
            cell: defaultdict(int) for cell in ordered
        }

        def backtrack(position: int, mines_used: int) -> None:
            if position == len(ordered):
                solutions_by_mines[mines_used] += 1
                for i, cell in enumerate(ordered):
                    if assignment[i]:
                        cell_mine_counts[cell][mines_used] += 1
                return
            for is_mine in (False, True):
                if is_mine and mines_used == mines_cap:
                    continue
                consistent = True
                for constraint_index in touching[position]:
                    undecided[constraint_index] -= 1
                    assigned[constraint_index] += is_mine
                    if (
                        assigned[constraint_index] > required[constraint_index]
                        or assigned[constraint_index] + undecided[constraint_index]
                        < required[constraint_index]
                    ):
                        consistent = False
                if consistent:
                    assignment[position] = is_mine
                    backtrack(position + 1, mines_used + is_mine)
                    assignment[position] = False
                for constraint_index in touching[position]:
                    undecided[constraint_index] += 1
                    assigned[constraint_index] -= is_mine

        backtrack(0, 0)
        if not solutions_by_mines:
            return None
        return dict(solutions_by_mines), cell_mine_counts

    def _probabilities(
        self,
    ) -> tuple[dict[Coord, float], set[Coord], set[Coord]]:
        """Mine probability for every hidden cell, plus proven-safe/mine sets.

        When every frontier component is small enough to enumerate, the
        probabilities are exact over ALL possibilities: each component's
        layouts are combined with every other component's and weighted by how
        many ways the leftover mines fit in the unexplored cells
        (C(off_frontier, mines_left - used)). Certainties are detected with
        integer arithmetic, so 0%/100% are proofs, not rounding.
        """
        constraints = self._constraints()
        hidden = set(self._hidden_cells())
        mines_left = self.field.mine_count - len(self._flagged_cells())

        enumerated: list[
            tuple[list[Coord], dict[int, int], dict[Coord, dict[int, int]]]
        ] = []
        heuristic: dict[Coord, float] = {}
        frontier: set[Coord] = set()

        for cells, component_constraints in self._components(constraints):
            frontier.update(cells)
            result = self._enumerate_component(cells, component_constraints, mines_left)
            if result is not None:
                enumerated.append((cells, result[0], result[1]))
            else:
                # Fallback: each cell gets the max density of its constraints.
                for cell in cells:
                    heuristic[cell] = max(
                        constraint.mines / len(constraint.cells)
                        for constraint in component_constraints
                        if cell in constraint.cells
                    )

        off_frontier = sorted(hidden - frontier)

        if not heuristic:
            exact = self._exact_probabilities(enumerated, off_frontier, mines_left)
            if exact is not None:
                return exact

        # Some component was too big (or the weighting degenerated): fall back
        # to per-component averages. Unanimous verdicts are still proofs.
        probabilities: dict[Coord, float] = {}
        certain_safe: set[Coord] = set()
        certain_mine: set[Coord] = set()
        expected_frontier_mines = 0.0

        for cells, solutions_by_mines, cell_mine_counts in enumerated:
            total = sum(solutions_by_mines.values())
            for cell in cells:
                mine_count = sum(cell_mine_counts[cell].values())
                probabilities[cell] = mine_count / total
                expected_frontier_mines += probabilities[cell]
                if mine_count == 0:
                    certain_safe.add(cell)
                elif mine_count == total:
                    certain_mine.add(cell)
        for cell, density in heuristic.items():
            probabilities[cell] = density
            expected_frontier_mines += density

        if off_frontier:
            remaining = max(mines_left - expected_frontier_mines, 0.0)
            density = min(remaining / len(off_frontier), 1.0)
            for cell in off_frontier:
                probabilities[cell] = density

        return probabilities, certain_safe, certain_mine

    def _exact_probabilities(
        self,
        enumerated: list[tuple[list[Coord], dict[int, int], dict[Coord, dict[int, int]]]],
        off_frontier: list[Coord],
        mines_left: int,
    ) -> tuple[dict[Coord, float], set[Coord], set[Coord]] | None:
        """Joint probabilities over every component plus the unexplored cells."""
        cells_off = len(off_frontier)

        def off_placements(remaining: int) -> int:
            if 0 <= remaining <= cells_off:
                return math.comb(cells_off, remaining)
            return 0

        def convolve(polynomials: list[dict[int, int]]) -> dict[int, int]:
            combined = {0: 1}
            for polynomial in polynomials:
                next_combined: dict[int, int] = defaultdict(int)
                for a, count_a in combined.items():
                    for b, count_b in polynomial.items():
                        next_combined[a + b] += count_a * count_b
                combined = dict(next_combined)
            return combined

        polynomials = [solutions for _, solutions, _ in enumerated]
        combined_all = convolve(polynomials)
        total_weight = sum(
            count * off_placements(mines_left - used)
            for used, count in combined_all.items()
        )
        if total_weight == 0:
            return None

        probabilities: dict[Coord, float] = {}
        certain_safe: set[Coord] = set()
        certain_mine: set[Coord] = set()

        for index, (cells, solutions_by_mines, cell_mine_counts) in enumerate(enumerated):
            others = convolve(
                [polynomial for j, polynomial in enumerate(polynomials) if j != index]
            )
            # weight_by_mines[k]: global weight of one layout using k mines here.
            weight_by_mines = {
                k: sum(
                    other_count * off_placements(mines_left - k - other_used)
                    for other_used, other_count in others.items()
                )
                for k in solutions_by_mines
            }
            for cell in cells:
                numerator = sum(
                    count * weight_by_mines[k]
                    for k, count in cell_mine_counts[cell].items()
                )
                probabilities[cell] = numerator / total_weight
                if numerator == 0:
                    certain_safe.add(cell)
                elif numerator == total_weight:
                    certain_mine.add(cell)

        if off_frontier:
            numerator = sum(
                count * off_placements(mines_left - used) * (mines_left - used)
                for used, count in combined_all.items()
            )
            probability = numerator / (total_weight * cells_off)
            for cell in off_frontier:
                probabilities[cell] = probability
            if numerator == 0:
                certain_safe.update(off_frontier)
            elif numerator == total_weight * cells_off:
                certain_mine.update(off_frontier)

        return probabilities, certain_safe, certain_mine

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

        # Cheap rules are exhausted; check every remaining possibility across
        # the whole board before conceding a guess.
        probabilities, certain_safe, certain_mine = self._probabilities()
        certain = [
            Move("flag", cell, "proven mine (enumeration)")
            for cell in sorted(certain_mine)
        ]
        certain += [
            Move("reveal", cell, "proven safe (enumeration)")
            for cell in sorted(certain_safe)
        ]
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
    HIT_MINE_COLOR = "#212121"
    FLAGGED_MINE_COLOR = "#43a047"

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
        self.hit_cell: Coord | None = None
        self.flagged_mines: set[Coord] = set()
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
            if self.field.game_over and not self.field.won:
                self.hit_cell = move.cell
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
            # Show every mine so the losing guess is visible in context,
            # remembering which ones the solver had already flagged.
            for row_index, row in enumerate(self.field.cells):
                for column_index, cell in enumerate(row):
                    if cell.is_mine:
                        if cell.state is CellState.FLAGGED:
                            self.flagged_mines.add((row_index, column_index))
                        cell.state = CellState.REVEALED
            self._refresh_all()
            self.status_text.set(
                f"Hit the black mine at {self.hit_cell} after {self.move_count} moves "
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
                    if (row, column) == self.hit_cell:
                        label.configure(
                            text="✹",
                            fg="#ff5252",
                            bg=self.HIT_MINE_COLOR,
                            relief=tk.SUNKEN,
                        )
                    elif (row, column) in self.flagged_mines:
                        label.configure(
                            text="⚑",
                            fg="white",
                            bg=self.FLAGGED_MINE_COLOR,
                            relief=tk.SUNKEN,
                        )
                    else:
                        label.configure(
                            text="✹", fg="white", bg="#d32f2f", relief=tk.SUNKEN
                        )
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
