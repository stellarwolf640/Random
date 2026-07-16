"""A complete Minesweeper game using only Python's standard library.

Run with:
    python minesweeper.py
"""

from __future__ import annotations

import random
import tkinter as tk
from dataclasses import dataclass
from enum import Enum, auto
from tkinter import messagebox, ttk
from typing import Iterable


Coord = tuple[int, int]


class CellState(Enum):
    HIDDEN = auto()
    REVEALED = auto()
    FLAGGED = auto()


@dataclass
class Cell:
    is_mine: bool = False
    adjacent_mines: int = 0
    state: CellState = CellState.HIDDEN


class Minefield:
    """Minesweeper rules and board state, independent of the GUI."""

    def __init__(
        self,
        rows: int,
        columns: int,
        mine_count: int,
        rng: random.Random | None = None,
    ) -> None:
        if rows <= 0 or columns <= 0:
            raise ValueError("Board dimensions must be positive.")
        if not 0 < mine_count < rows * columns:
            raise ValueError("Mine count must be between 1 and the number of cells minus 1.")

        self.rows = rows
        self.columns = columns
        self.mine_count = mine_count
        self._rng = rng or random.Random()
        self.cells = [[Cell() for _ in range(columns)] for _ in range(rows)]
        self.mines_placed = False
        self.game_over = False
        self.won = False

    def in_bounds(self, row: int, column: int) -> bool:
        return 0 <= row < self.rows and 0 <= column < self.columns

    def neighbors(self, row: int, column: int) -> Iterable[Coord]:
        for row_offset in (-1, 0, 1):
            for column_offset in (-1, 0, 1):
                if row_offset == 0 and column_offset == 0:
                    continue
                neighbor = (row + row_offset, column + column_offset)
                if self.in_bounds(*neighbor):
                    yield neighbor

    def _place_mines(self, safe_row: int, safe_column: int) -> None:
        # Keep the first clicked cell and its neighbors clear whenever the board
        # has enough room. On very dense boards, only the clicked cell is safe.
        protected = {(safe_row, safe_column), *self.neighbors(safe_row, safe_column)}
        all_positions = [
            (row, column)
            for row in range(self.rows)
            for column in range(self.columns)
        ]
        candidates = [position for position in all_positions if position not in protected]
        if len(candidates) < self.mine_count:
            candidates = [
                position for position in all_positions if position != (safe_row, safe_column)
            ]

        for row, column in self._rng.sample(candidates, self.mine_count):
            self.cells[row][column].is_mine = True

        for row in range(self.rows):
            for column in range(self.columns):
                self.cells[row][column].adjacent_mines = sum(
                    self.cells[n_row][n_column].is_mine
                    for n_row, n_column in self.neighbors(row, column)
                )
        self.mines_placed = True

    @property
    def flag_count(self) -> int:
        return sum(
            cell.state is CellState.FLAGGED
            for row in self.cells
            for cell in row
        )

    def toggle_flag(self, row: int, column: int) -> bool:
        """Toggle a hidden cell's flag and return whether it changed."""
        if self.game_over or not self.in_bounds(row, column):
            return False
        cell = self.cells[row][column]
        if cell.state is CellState.REVEALED:
            return False
        cell.state = (
            CellState.HIDDEN if cell.state is CellState.FLAGGED else CellState.FLAGGED
        )
        return True

    def reveal(self, row: int, column: int) -> set[Coord]:
        """Reveal a cell, expanding empty areas, and return changed positions."""
        if self.game_over or not self.in_bounds(row, column):
            return set()
        starting_cell = self.cells[row][column]
        if starting_cell.state is not CellState.HIDDEN:
            return set()

        if not self.mines_placed:
            self._place_mines(row, column)
            starting_cell = self.cells[row][column]

        changed: set[Coord] = set()
        if starting_cell.is_mine:
            starting_cell.state = CellState.REVEALED
            changed.add((row, column))
            self.game_over = True
            return changed

        pending = [(row, column)]
        while pending:
            current_row, current_column = pending.pop()
            cell = self.cells[current_row][current_column]
            if cell.state is not CellState.HIDDEN or cell.is_mine:
                continue

            cell.state = CellState.REVEALED
            changed.add((current_row, current_column))
            if cell.adjacent_mines == 0:
                pending.extend(self.neighbors(current_row, current_column))

        self._check_for_win()
        return changed

    def chord(self, row: int, column: int) -> set[Coord]:
        """Reveal neighbors when a number has the matching number of flags."""
        if self.game_over or not self.in_bounds(row, column):
            return set()
        cell = self.cells[row][column]
        if cell.state is not CellState.REVEALED or cell.adjacent_mines == 0:
            return set()

        nearby = list(self.neighbors(row, column))
        flagged = sum(
            self.cells[n_row][n_column].state is CellState.FLAGGED
            for n_row, n_column in nearby
        )
        if flagged != cell.adjacent_mines:
            return set()

        changed: set[Coord] = set()
        for neighbor_row, neighbor_column in nearby:
            if self.cells[neighbor_row][neighbor_column].state is CellState.HIDDEN:
                changed.update(self.reveal(neighbor_row, neighbor_column))
                if self.game_over:
                    break
        return changed

    def _check_for_win(self) -> None:
        hidden_safe_cells = any(
            not cell.is_mine and cell.state is not CellState.REVEALED
            for row in self.cells
            for cell in row
        )
        if self.mines_placed and not hidden_safe_cells:
            self.won = True
            self.game_over = True
            for row in self.cells:
                for cell in row:
                    if cell.is_mine:
                        cell.state = CellState.FLAGGED


DIFFICULTIES = {
    "Beginner": (9, 9, 10),
    "Intermediate": (16, 16, 40),
    "Expert": (16, 30, 99),
    "Impossible": (32, 64, 512)
}


class MinesweeperApp:
    NUMBER_COLORS = {
        1: "#1976d2",
        2: "#2e7d32",
        3: "#d32f2f",
        4: "#512da8",
        5: "#7f0000",
        6: "#00838f",
        7: "#212121",
        8: "#616161",
    }
    HIDDEN_COLOR = "#bdbdbd"
    REVEALED_COLOR = "#eeeeee"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Minesweeper")
        self.root.resizable(False, False)

        self.difficulty = tk.StringVar(value="Beginner")
        self.mine_text = tk.StringVar()
        self.time_text = tk.StringVar(value="Time: 0")
        self.status_text = tk.StringVar(value="Clear the field without hitting a mine.")
        self.elapsed_seconds = 0
        self.timer_job: str | None = None
        self.timer_started = False
        self.buttons: list[list[tk.Button]] = []

        self._build_controls()
        self.board_frame = ttk.Frame(root, padding=(10, 0, 10, 8))
        self.board_frame.grid(row=1, column=0)
        ttk.Label(root, textvariable=self.status_text, anchor="center").grid(
            row=2, column=0, sticky="ew", padx=10, pady=(0, 8)
        )
        self.new_game()

    def _build_controls(self) -> None:
        controls = ttk.Frame(self.root, padding=10)
        controls.grid(row=0, column=0, sticky="ew")

        ttk.Label(controls, text="Difficulty:").grid(row=0, column=0, padx=(0, 4))
        selector = ttk.Combobox(
            controls,
            textvariable=self.difficulty,
            values=list(DIFFICULTIES),
            state="readonly",
            width=12,
        )
        selector.grid(row=0, column=1, padx=(0, 10))
        selector.bind("<<ComboboxSelected>>", lambda _event: self.new_game())
        ttk.Button(controls, text="New Game", command=self.new_game).grid(
            row=0, column=2, padx=(0, 12)
        )
        ttk.Label(controls, textvariable=self.mine_text, width=12).grid(row=0, column=3)
        ttk.Label(controls, textvariable=self.time_text, width=10).grid(row=0, column=4)

    def new_game(self) -> None:
        self._stop_timer()
        self.elapsed_seconds = 0
        self.timer_started = False
        self.time_text.set("Time: 0")
        self.status_text.set("Left-click to reveal. Right-click to flag.")

        rows, columns, mines = DIFFICULTIES[self.difficulty.get()]
        self.field = Minefield(rows, columns, mines)
        for widget in self.board_frame.winfo_children():
            widget.destroy()

        self.buttons = []
        button_size = 2 if columns <= 16 else 1
        for row in range(rows):
            button_row: list[tk.Button] = []
            for column in range(columns):
                button = tk.Button(
                    self.board_frame,
                    text="",
                    width=button_size,
                    height=1,
                    font=("Segoe UI", 10, "bold"),
                    bg=self.HIDDEN_COLOR,
                    activebackground="#cccccc",
                    relief=tk.RAISED,
                    borderwidth=2,
                    command=lambda r=row, c=column: self._reveal(r, c),
                )
                button.grid(row=row, column=column, sticky="nsew")
                button.bind(
                    "<Button-3>", lambda event, r=row, c=column: self._flag(event, r, c)
                )
                button.bind(
                    "<Button-2>", lambda event, r=row, c=column: self._flag(event, r, c)
                )
                button.bind(
                    "<Double-Button-1>",
                    lambda event, r=row, c=column: self._chord(event, r, c),
                )
                button_row.append(button)
            self.buttons.append(button_row)
        self._refresh_all()

    def _start_timer(self) -> None:
        if not self.timer_started and not self.field.game_over:
            self.timer_started = True
            self.timer_job = self.root.after(1000, self._tick)

    def _tick(self) -> None:
        self.timer_job = None
        if self.field.game_over:
            return
        self.elapsed_seconds += 1
        self.time_text.set(f"Time: {self.elapsed_seconds}")
        self.timer_job = self.root.after(1000, self._tick)

    def _stop_timer(self) -> None:
        if self.timer_job is not None:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None

    def _reveal(self, row: int, column: int) -> None:
        if self.field.game_over:
            return
        self._start_timer()
        self.field.reveal(row, column)
        self._refresh_all()
        self._handle_finished_game()

    def _flag(self, _event: tk.Event, row: int, column: int) -> str:
        if self.field.toggle_flag(row, column):
            self._refresh_cell(row, column)
            self._update_mine_counter()
        return "break"

    def _chord(self, _event: tk.Event, row: int, column: int) -> str:
        if not self.field.game_over:
            self._start_timer()
            self.field.chord(row, column)
            self._refresh_all()
            self._handle_finished_game()
        return "break"

    def _refresh_all(self) -> None:
        for row in range(self.field.rows):
            for column in range(self.field.columns):
                self._refresh_cell(row, column)
        self._update_mine_counter()

    def _refresh_cell(self, row: int, column: int) -> None:
        cell = self.field.cells[row][column]
        button = self.buttons[row][column]

        if cell.state is CellState.FLAGGED:
            button.configure(text="⚑", fg="#c62828", bg=self.HIDDEN_COLOR, relief=tk.RAISED)
        elif cell.state is CellState.HIDDEN:
            button.configure(text="", fg="black", bg=self.HIDDEN_COLOR, relief=tk.RAISED)
        elif cell.is_mine:
            button.configure(text="✹", fg="white", bg="#d32f2f", relief=tk.SUNKEN)
        else:
            number = cell.adjacent_mines
            button.configure(
                text=str(number) if number else "",
                fg=self.NUMBER_COLORS.get(number, "black"),
                bg=self.REVEALED_COLOR,
                relief=tk.SUNKEN,
            )

    def _update_mine_counter(self) -> None:
        remaining = self.field.mine_count - self.field.flag_count
        self.mine_text.set(f"Mines: {remaining}")

    def _handle_finished_game(self) -> None:
        if not self.field.game_over:
            return
        self._stop_timer()
        if self.field.won:
            self.status_text.set(f"You won in {self.elapsed_seconds} seconds!")
            self._refresh_all()
            messagebox.showinfo("Minesweeper", "You cleared the minefield!")
            return

        self.status_text.set("Mine hit — game over.")
        for row in range(self.field.rows):
            for column in range(self.field.columns):
                cell = self.field.cells[row][column]
                if cell.is_mine:
                    cell.state = CellState.REVEALED
        self._refresh_all()
        messagebox.showerror("Minesweeper", "Boom! You hit a mine.")


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    MinesweeperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
