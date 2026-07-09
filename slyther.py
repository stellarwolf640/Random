import os
import random
import sys
import time

WIDTH = 30
HEIGHT = 15
TICK_RATE = 0.11


# Cross-platform key reading
if os.name == "nt":
    import msvcrt

    def get_key():
        if not msvcrt.kbhit():
            return None

        key = msvcrt.getch()

        # Arrow keys on Windows begin with b'\xe0' or b'\x00'
        if key in (b"\xe0", b"\x00"):
            arrow = msvcrt.getch()
            return {
                b"H": "UP",
                b"P": "DOWN",
                b"K": "LEFT",
                b"M": "RIGHT",
            }.get(arrow)

        return key.decode(errors="ignore").lower()

else:
    import select
    import termios
    import tty

    def get_key():
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None

        key = sys.stdin.read(1)

        if key == "\x1b":
            extra = sys.stdin.read(2)
            return {
                "[A": "UP",
                "[B": "DOWN",
                "[D": "LEFT",
                "[C": "RIGHT",
            }.get(extra)

        return key.lower()


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def draw(snake, food, score):
    clear()

    snake_set = set(snake)

    print(f" Tiny Terminal Snake   Score: {score}")
    print("+" + "-" * (WIDTH * 2) + "+")

    for y in range(HEIGHT):
        row = "|"

        for x in range(WIDTH):
            pos = (x, y)

            if pos == snake[0]:
                row += "[]"
            elif pos in snake_set:
                row += "##"
            elif pos == food:
                row += "**"
            else:
                row += "  "

        print(row + "|")

    print("+" + "-" * (WIDTH * 2) + "+")
    print("WASD / Arrow Keys to move | Q to quit")


def new_food(snake):
    while True:
        food = (
            random.randint(0, WIDTH - 1),
            random.randint(0, HEIGHT - 1),
        )
        if food not in snake:
            return food


def change_direction(current, key):
    directions = {
        "w": (0, -1),
        "UP": (0, -1),
        "s": (0, 1),
        "DOWN": (0, 1),
        "a": (-1, 0),
        "LEFT": (-1, 0),
        "d": (1, 0),
        "RIGHT": (1, 0),
    }

    new_direction = directions.get(key)

    if not new_direction:
        return current

    # Prevent reversing directly into yourself
    if new_direction == (-current[0], -current[1]):
        return current

    return new_direction


def game():
    snake = [
        (WIDTH // 2, HEIGHT // 2),
        (WIDTH // 2 - 1, HEIGHT // 2),
        (WIDTH // 2 - 2, HEIGHT // 2),
    ]

    direction = (1, 0)
    food = new_food(snake)
    score = 0

    old_terminal_settings = None

    # Put Linux/macOS terminal into character mode
    if os.name != "nt":
        old_terminal_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

    try:
        while True:
            start = time.time()

            key = get_key()

            if key == "q":
                break

            direction = change_direction(direction, key)

            head_x, head_y = snake[0]
            new_head = (
                head_x + direction[0],
                head_y + direction[1],
            )

            hit_wall = (
                new_head[0] < 0
                or new_head[0] >= WIDTH
                or new_head[1] < 0
                or new_head[1] >= HEIGHT
            )

            hit_self = new_head in snake

            if hit_wall or hit_self:
                draw(snake, food, score)
                print("\nGame over.")
                break

            snake.insert(0, new_head)

            if new_head == food:
                score += 1
                food = new_food(snake)
            else:
                snake.pop()

            draw(snake, food, score)

            remaining_time = TICK_RATE - (time.time() - start)
            if remaining_time > 0:
                time.sleep(remaining_time)

    finally:
        if old_terminal_settings:
            termios.tcsetattr(
                sys.stdin,
                termios.TCSADRAIN,
                old_terminal_settings,
            )


if __name__ == "__main__":
    game()