import os
import random
import sys
import time
from collections import deque

WIDTH = 10
HEIGHT = 5
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
MAX_STRETCH_DETOURS = 32
LATE_STRETCH_DETOURS = 48
ENDGAME_STRETCH_DETOURS = 64
SMALL_POCKET_LIMIT = 8

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


def detour_options(start, end):
    if manhattan_distance(start, end) != 1:
        return []

    if start[0] == end[0]:
        offsets = ((-1, 0), (1, 0))
    else:
        offsets = ((0, -1), (0, 1))

    options = []

    for offset in offsets:
        first = add_positions(start, offset)
        second = add_positions(end, offset)

        if in_bounds(first) and in_bounds(second):
            options.append((first, second))

    return options


def open_neighbor_count(position, blocked):
    count = 0

    for direction in DIRECTION_ORDER:
        neighbor = add_positions(position, direction)

        if in_bounds(neighbor) and neighbor not in blocked:
            count += 1

    return count


def stretch_detour_limit(snake):
    filled_ratio = len(snake) / (WIDTH * HEIGHT)

    if filled_ratio >= 0.65:
        return ENDGAME_STRETCH_DETOURS

    if filled_ratio >= 0.35:
        return LATE_STRETCH_DETOURS

    return MAX_STRETCH_DETOURS


def stretch_path(snake, path, blocked_extra=None, max_detours=MAX_STRETCH_DETOURS):
    if not path:
        return []

    blocked = set(snake[:-1])

    if blocked_extra:
        blocked.update(blocked_extra)

    full_path = [snake[0]] + path[:]
    reserved = set(full_path)
    detours_added = 0

    while detours_added < max_detours:
        changed = False
        index = 0

        while index < len(full_path) - 1 and detours_added < max_detours:
            start = full_path[index]
            end = full_path[index + 1]
            best_detour = None
            best_score = None

            for first, second in detour_options(start, end):
                if (
                    first in blocked
                    or second in blocked
                    or first in reserved
                    or second in reserved
                ):
                    continue

                blocked_with_detour = blocked | reserved
                open_cells = (
                    open_neighbor_count(first, blocked_with_detour)
                    + open_neighbor_count(second, blocked_with_detour)
                )
                pocket_bonus = 1 if open_cells <= 4 else 0
                score = (pocket_bonus, -open_cells, first[1], first[0])

                if best_score is None or score > best_score:
                    best_score = score
                    best_detour = (first, second)

            if best_detour:
                first, second = best_detour
                full_path[index + 1:index + 1] = [first, second]
                reserved.add(first)
                reserved.add(second)
                detours_added += 1
                changed = True
                index += 2

            index += 1

        if not changed:
            break

    return full_path[1:]


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


def open_space_stats(blocked):
    visited = set()
    region_count = 0
    largest_region = 0
    small_pocket_penalty = 0

    for y in range(HEIGHT):
        for x in range(WIDTH):
            position = (x, y)

            if position in blocked or position in visited:
                continue

            region_count += 1
            queue = deque([position])
            visited.add(position)
            region_size = 0

            while queue:
                current = queue.popleft()
                region_size += 1

                for direction in DIRECTION_ORDER:
                    neighbor = add_positions(current, direction)

                    if (
                        in_bounds(neighbor)
                        and neighbor not in blocked
                        and neighbor not in visited
                    ):
                        visited.add(neighbor)
                        queue.append(neighbor)

            largest_region = max(largest_region, region_size)

            if region_size <= SMALL_POCKET_LIMIT:
                small_pocket_penalty += SMALL_POCKET_LIMIT - region_size + 1

    return small_pocket_penalty, largest_region, region_count


def head_can_reach_tail(snake):
    if len(snake) >= WIDTH * HEIGHT:
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
        tail_path = bfs_path(updated_snake, updated_snake[-1], direction)
        tail_is_reachable = bool(tail_path)
        long_tail_path = stretch_path(
            updated_snake,
            tail_path,
            max_detours=stretch_detour_limit(updated_snake),
        )
        tail_room = len(long_tail_path)
        small_pocket_penalty, largest_region, region_count = open_space_stats(blocked)
        food_distance = (
            manhattan_distance(new_head, food)
            if food is not None
            else 0
        )
        score = (
            tail_is_reachable,
            -small_pocket_penalty,
            tail_room,
            reachable_cells,
            largest_region,
            -region_count,
            food_distance,
        )

        if best_score is None or score > best_score:
            best_score = score
            best_direction = direction

    return best_direction


def choose_hamiltonian_direction(snake, food, current_direction):
    if not snake_is_cycle_ordered(snake):
        return None

    head = snake[0]
    tail = snake[-1]
    tail_distance = cycle_distance(head, tail)
    best_direction = None
    best_score = None

    for direction in preferred_directions(current_direction):
        if (
            direction == (-current_direction[0], -current_direction[1])
            or not can_move(snake, direction, food)
        ):
            continue

        new_head = add_positions(head, direction)
        jump_distance = cycle_distance(head, new_head)

        if jump_distance == 0 or jump_distance >= tail_distance:
            continue

        updated_snake = simulate_move(snake, new_head, food)
        updated_tail_distance = cycle_distance(updated_snake[0], updated_snake[-1])
        food_distance = (
            cycle_distance(updated_snake[0], food)
            if food is not None
            else 0
        )
        food_is_ahead = food is not None and food_distance < updated_tail_distance
        cycle_step = 1 if new_head == cycle_successor(head) else 0
        space_after_move = updated_tail_distance

        score = (
            food_is_ahead,
            -food_distance if food_is_ahead else 0,
            space_after_move,
            cycle_step,
            -jump_distance,
        )

        if best_score is None or score > best_score:
            best_score = score
            best_direction = direction

    return best_direction


def choose_ai_direction(snake, food, current_direction):
    hamiltonian_direction = choose_hamiltonian_direction(
        snake,
        food,
        current_direction,
    )

    if hamiltonian_direction:
        return hamiltonian_direction

    food_path = bfs_path(snake, food, current_direction)

    if food_path:
        after_food = simulate_path(snake, food_path, food)

        if head_can_reach_tail(after_food):
            return direction_between(snake[0], food_path[0])

    blocked_food = {food} if food is not None else None
    tail_path = bfs_path(snake, snake[-1], current_direction, blocked_food)

    if tail_path:
        long_tail_path = stretch_path(
            snake,
            tail_path,
            blocked_food,
            max_detours=stretch_detour_limit(snake),
        )
        tail_direction = first_safe_direction(
            snake,
            long_tail_path,
            food,
            current_direction,
        )

        if tail_direction:
            return tail_direction

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
