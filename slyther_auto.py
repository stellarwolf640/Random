import os
import random
import sys
import time
from collections import deque

WIDTH = 50
HEIGHT = 20
TICK_RATE = 0.11
AUTO_PLAY = True
SPEED_KEYS = {
    "f": 4,
    "g": 16,
    "h": 32,
    "j": 64,
    "k": 0,
}
MAX_SPEED_DRAW_INTERVAL = 128

# How much a shortcut is penalized per empty cell it jumps over. Skipped
# empty cells become holes behind the head, and an apple spawning in a
# hole costs a full trip around the board to reach.
HOLE_PENALTY = 1

DIRECTIONS = {
    "w": (0, -1),
    "UP": (0, -1),
    "s": (0, 1),
    "DOWN": (0, 1),
    "a": (-1, 0),
    "LEFT": (-1, 0),
    "d": (1, 0),
    "RIGHT": (1, 0),
}

DIRECTION_ORDER = (
    (0, -1),
    (1, 0),
    (0, 1),
    (-1, 0),
)

BOARD_SIZE = WIDTH * HEIGHT


def build_hamiltonian_cycle():
    cycle = [(0, y) for y in range(HEIGHT)]
    cycle.extend((x, HEIGHT - 1) for x in range(1, WIDTH))

    for x in range(WIDTH - 1, 0, -1):
        if x % 2:
            y_values = range(HEIGHT - 2, -1, -1)
        else:
            y_values = range(0, HEIGHT - 1)

        cycle.extend((x, y) for y in y_values)

    if len(cycle) != BOARD_SIZE or len(set(cycle)) != BOARD_SIZE:
        raise ValueError("Hamiltonian cycle does not cover the board")

    for index, position in enumerate(cycle):
        next_position = cycle[(index + 1) % BOARD_SIZE]

        if (
            abs(position[0] - next_position[0])
            + abs(position[1] - next_position[1])
            != 1
        ):
            raise ValueError("Hamiltonian cycle contains a broken edge")

    return cycle


HAMILTONIAN_CYCLE = build_hamiltonian_cycle()
CYCLE_INDEX = {
    position: index
    for index, position in enumerate(HAMILTONIAN_CYCLE)
}


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


def draw(snake, food, score, auto_play, speed_multiplier):
    clear()

    snake_set = set(snake)
    mode = "AI" if auto_play else "Manual"
    speed = "MAX" if speed_multiplier == 0 else f"{speed_multiplier}x"

    print(f" Tiny Terminal Snake   Score: {score}   Mode: {mode}   Speed: {speed}")
    print("+" + "-" * (WIDTH * 2) + "+")

    for y in range(HEIGHT):
        row = "|"

        for x in range(WIDTH):
            pos = (x, y)

            if pos == snake[0]:
                row += "[]"
            elif pos in snake_set:
                row += "##"
            elif food is not None and pos == food:
                row += "**"
            else:
                row += "  "

        print(row + "|")

    print("+" + "-" * (WIDTH * 2) + "+")
    print("P to toggle AI | F/G/H/J/K speed | WASD / Arrow Keys | Q to quit")


def new_food(snake):
    snake_set = set(snake)
    open_cells = [
        (x, y)
        for y in range(HEIGHT)
        for x in range(WIDTH)
        if (x, y) not in snake_set
    ]

    if not open_cells:
        return None

    return random.choice(open_cells)


def change_direction(current, key):
    new_direction = DIRECTIONS.get(key)

    if not new_direction:
        return current

    # Prevent reversing directly into yourself
    if new_direction == (-current[0], -current[1]):
        return current

    return new_direction


def in_bounds(position):
    x, y = position
    return 0 <= x < WIDTH and 0 <= y < HEIGHT


def add_positions(position, direction):
    return position[0] + direction[0], position[1] + direction[1]


def direction_between(start, end):
    return end[0] - start[0], end[1] - start[1]


def manhattan_distance(start, end):
    return abs(start[0] - end[0]) + abs(start[1] - end[1])


def cycle_distance(start, end):
    return (CYCLE_INDEX[end] - CYCLE_INDEX[start]) % BOARD_SIZE


def cycle_backward_distance(start, end):
    return (CYCLE_INDEX[start] - CYCLE_INDEX[end]) % BOARD_SIZE


def cycle_successor(position):
    return HAMILTONIAN_CYCLE[(CYCLE_INDEX[position] + 1) % BOARD_SIZE]


def make_starting_snake(length=3):
    head = (WIDTH // 2, HEIGHT // 2)
    head_index = CYCLE_INDEX[head]

    return [
        HAMILTONIAN_CYCLE[(head_index - offset) % BOARD_SIZE]
        for offset in range(length)
    ]


def snake_is_cycle_ordered(snake):
    if len(snake) < 2:
        return True

    total_backward_distance = 0

    for index in range(1, len(snake)):
        segment_distance = cycle_backward_distance(
            snake[index - 1],
            snake[index],
        )

        if segment_distance == 0:
            return False

        total_backward_distance += segment_distance

        if total_backward_distance >= BOARD_SIZE:
            return False

    return True


def preferred_directions(current_direction):
    ordered = []

    if current_direction in DIRECTION_ORDER:
        ordered.append(current_direction)

    for direction in DIRECTION_ORDER:
        if direction not in ordered:
            ordered.append(direction)

    return ordered


def can_move(snake, direction, food):
    new_head = add_positions(snake[0], direction)

    if not in_bounds(new_head):
        return False

    will_grow = food is not None and new_head == food
    occupied = set(snake if will_grow else snake[:-1])
    return new_head not in occupied


def bfs_path(snake, goal, current_direction=None, blocked_extra=None):
    if goal is None:
        return []

    start = snake[0]

    if start == goal:
        return []

    blocked = set(snake[:-1])

    if blocked_extra:
        blocked.update(blocked_extra)

    blocked.discard(goal)

    queue = deque([start])
    previous = {start: None}

    while queue:
        position = queue.popleft()

        if position == goal:
            break

        for direction in preferred_directions(current_direction):
            if (
                position == start
                and current_direction is not None
                and direction == (-current_direction[0], -current_direction[1])
            ):
                continue

            next_position = add_positions(position, direction)

            if (
                not in_bounds(next_position)
                or next_position in blocked
                or next_position in previous
            ):
                continue

            previous[next_position] = position
            queue.append(next_position)

    if goal not in previous:
        return []

    path = []
    position = goal

    while position != start:
        path.append(position)
        position = previous[position]

    path.reverse()
    return path


def first_safe_direction(snake, path, food, current_direction):
    if not path:
        return None

    direction = direction_between(snake[0], path[0])

    if direction == (-current_direction[0], -current_direction[1]):
        return None

    if not can_move(snake, direction, food):
        return None

    return direction


def simulate_move(snake, new_head, food):
    updated_snake = [new_head] + snake[:]

    if food is None or new_head != food:
        updated_snake.pop()

    return updated_snake


def simulate_path(snake, path, food):
    simulated_snake = snake[:]

    for position in path:
        simulated_snake = simulate_move(simulated_snake, position, food)

    return simulated_snake


def flood_fill_count(start, blocked):
    if not in_bounds(start) or start in blocked:
        return 0

    queue = deque([start])
    visited = {start}

    while queue:
        position = queue.popleft()

        for direction in DIRECTION_ORDER:
            next_position = add_positions(position, direction)

            if (
                in_bounds(next_position)
                and next_position not in blocked
                and next_position not in visited
            ):
                visited.add(next_position)
                queue.append(next_position)

    return len(visited)


def head_can_reach_tail(snake):
    if len(snake) >= BOARD_SIZE:
        return True

    return bool(bfs_path(snake, snake[-1]))


def safest_open_direction(snake, food, current_direction):
    best_direction = None
    best_score = None

    for direction in preferred_directions(current_direction):
        if (
            direction == (-current_direction[0], -current_direction[1])
            or not can_move(snake, direction, food)
        ):
            continue

        new_head = add_positions(snake[0], direction)
        updated_snake = simulate_move(snake, new_head, food)
        blocked = set(updated_snake[:-1])
        reachable_cells = flood_fill_count(updated_snake[0], blocked)
        tail_is_reachable = head_can_reach_tail(updated_snake)
        food_distance = (
            manhattan_distance(new_head, food)
            if food is not None
            else 0
        )
        score = (
            tail_is_reachable,
            reachable_cells,
            -food_distance,
        )

        if best_score is None or score > best_score:
            best_score = score
            best_direction = direction

    return best_direction


def empty_cells_skipped(snake_set, head, new_head):
    """Count empty cells the move jumps over along the cycle.

    Skipped empty cells end up behind the head, where the next apple can
    spawn and force a wrap around the board. Skipping over body cells is
    free: they hold no future apples.
    """
    start_index = CYCLE_INDEX[head]
    jump = cycle_distance(head, new_head)
    count = 0

    for offset in range(1, jump):
        cell = HAMILTONIAN_CYCLE[(start_index + offset) % BOARD_SIZE]

        if cell not in snake_set:
            count += 1

    return count


def choose_shortcut_direction(snake, food, current_direction):
    """Follow the Hamiltonian cycle, taking safe shortcuts toward the
    food while keeping the empty space consolidated ahead of the head.

    Positions are ranked by their cycle index relative to the tail. As
    long as every move lands strictly ahead of the head in that ranking,
    the body stays ordered along the cycle, so falling back to plain
    cycle-following can never collide. That makes shortcuts safe at any
    fill level without lookahead.

    Among safe moves the score trades apple distance against the holes a
    jump leaves behind, so the next apple tends to spawn in the snake's
    path instead of in a pocket that needs a full rotation to reach.
    """
    if not snake_is_cycle_ordered(snake):
        return None

    head = snake[0]
    tail = snake[-1]
    snake_set = set(snake)
    head_rank = cycle_distance(tail, head)
    food_rank = cycle_distance(tail, food) if food is not None else None
    food_is_ahead = food_rank is not None and food_rank > head_rank

    best_direction = None
    best_score = None

    for direction in DIRECTION_ORDER:
        if direction == (-current_direction[0], -current_direction[1]):
            continue

        if not can_move(snake, direction, food):
            continue

        new_head = add_positions(head, direction)
        new_rank = cycle_distance(tail, new_head)

        # Stepping into the tail cell is the furthest-forward move of
        # all: the tail vacates it this tick (food is never on the body,
        # so this move cannot grow).
        if new_head == tail:
            new_rank = BOARD_SIZE

        if new_rank <= head_rank:
            continue

        if food_is_ahead and new_rank > food_rank:
            continue

        food_distance = (
            cycle_distance(new_head, food) if food is not None else 0
        )
        holes_created = empty_cells_skipped(snake_set, head, new_head)
        score = food_distance + HOLE_PENALTY * holes_created

        if best_score is None or score < best_score:
            best_score = score
            best_direction = direction

    return best_direction


def choose_ai_direction(snake, food, current_direction):
    shortcut_direction = choose_shortcut_direction(
        snake,
        food,
        current_direction,
    )

    if shortcut_direction:
        return shortcut_direction

    # Fallback for when manual play has scrambled the cycle ordering:
    # chase the food if the tail stays reachable afterwards, otherwise
    # follow the tail, otherwise keep as much open space as possible.
    food_path = bfs_path(snake, food, current_direction)

    if food_path:
        after_food = simulate_path(snake, food_path, food)

        if head_can_reach_tail(after_food):
            return direction_between(snake[0], food_path[0])

    blocked_food = {food} if food is not None else None
    tail_path = bfs_path(snake, snake[-1], current_direction, blocked_food)
    tail_direction = first_safe_direction(
        snake,
        tail_path,
        food,
        current_direction,
    )

    if tail_direction:
        return tail_direction

    open_direction = safest_open_direction(snake, food, current_direction)

    if open_direction:
        return open_direction

    return current_direction


def game():
    snake = make_starting_snake()
    direction = direction_between(snake[0], cycle_successor(snake[0]))
    food = new_food(snake)
    score = 0
    auto_play = AUTO_PLAY
    speed_multiplier = 1
    frame_count = 0

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

            if key in SPEED_KEYS:
                selected_speed = SPEED_KEYS[key]
                speed_multiplier = (
                    1 if speed_multiplier == selected_speed else selected_speed
                )

            if key == "p":
                auto_play = not auto_play
            elif auto_play:
                direction = choose_ai_direction(snake, food, direction)
            else:
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

            will_grow = food is not None and new_head == food
            hit_self = new_head in (snake if will_grow else snake[:-1])

            if hit_wall or hit_self:
                draw(snake, food, score, auto_play, speed_multiplier)
                print("\nGame over.")
                break

            snake.insert(0, new_head)

            if will_grow:
                score += 1
                food = new_food(snake)

                if food is None:
                    draw(snake, food, score, auto_play, speed_multiplier)
                    print("\nYou filled the board. You win.")
                    break
            else:
                snake.pop()

            frame_count += 1
            draw_interval = (
                MAX_SPEED_DRAW_INTERVAL
                if speed_multiplier == 0
                else speed_multiplier
            )
            should_draw = (
                frame_count % draw_interval == 0
                or key in SPEED_KEYS
                or key == "p"
                or will_grow
            )

            if should_draw:
                draw(snake, food, score, auto_play, speed_multiplier)

            if speed_multiplier != 0:
                tick_rate = TICK_RATE / speed_multiplier
                remaining_time = tick_rate - (time.time() - start)
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
