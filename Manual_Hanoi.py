import json
import os
import time

MAX_RINGS = 10
SCORE_FILE = "hanoi_scores.json"


def load_scores():
    if not os.path.exists(SCORE_FILE):
        return {}

    try:
        with open(SCORE_FILE, "r") as file:
            return json.load(file)
    except json.JSONDecodeError:
        return {}


def save_scores(scores):
    with open(SCORE_FILE, "w") as file:
        json.dump(scores, file, indent=4)


def make_level(num_rings):
    disks = [chr(ord("A") + i) for i in range(num_rings)]
    sizes = {disk: num_rings - i for i, disk in enumerate(disks)}

    pegs = {
        1: disks.copy(),
        2: [],
        3: []
    }

    return disks, sizes, pegs


def print_pegs(pegs, move_count, num_rings):
    print(f"\nMove {move_count}")

    for level in range(num_rings - 1, -1, -1):
        row = []
        for peg in [1, 2, 3]:
            if level < len(pegs[peg]):
                row.append(pegs[peg][level])
            else:
                row.append("|")
        print(" ".join(row))

    print("1 2 3")
    print("-" * 6)


def is_valid_move(pegs, sizes, source, dest):
    if not pegs[source]:
        return False

    if not pegs[dest]:
        return True

    return sizes[pegs[source][-1]] < sizes[pegs[dest][-1]]


def move_disk(pegs, source, dest):
    disk = pegs[source].pop()
    pegs[dest].append(disk)


def is_solved(pegs, num_rings):
    return len(pegs[3]) == num_rings


def update_score(scores, level, move_count, elapsed_time):
    level_key = str(level)

    current_best = scores.get(level_key)

    new_score = {
        "moves": move_count,
        "time": round(elapsed_time, 2)
    }

    if current_best is None:
        scores[level_key] = new_score
        return "New score saved!"

    better_moves = move_count < current_best["moves"]
    same_moves_better_time = (
        move_count == current_best["moves"]
        and elapsed_time < current_best["time"]
    )

    if better_moves or same_moves_better_time:
        scores[level_key] = new_score
        return "New best score!"

    return "Score did not beat your best."


def get_highest_unlocked_level(scores):
    highest = 1

    for level in range(1, MAX_RINGS + 1):
        level_key = str(level)
        optimal = (2 ** level) - 1

        if level_key in scores and scores[level_key]["moves"] == optimal:
            highest = level + 1
        else:
            break

    return min(highest, MAX_RINGS)


def choose_starting_level(scores):
    highest_unlocked = get_highest_unlocked_level(scores)

    print("\nTower of Hanoi")
    print(f"Highest unlocked level: {highest_unlocked}")
    print("Press Enter to start at Level 1.")

    while True:
        choice = input(f"Choose a level from 1 to {highest_unlocked}: ").strip()

        if choice == "":
            return 1

        try:
            level = int(choice)

            if 1 <= level <= highest_unlocked:
                return level

            print(f"You can only choose levels 1 through {highest_unlocked}.")

        except ValueError:
            print("Enter a valid level number.")


def parse_move(user_input):
    user_input = user_input.strip().lower().replace(" ", "")

    if user_input in ["end", "e"]:
        return "end", None

    if len(user_input) != 2:
        return None, None

    if not user_input.isdigit():
        return None, None

    source = int(user_input[0])
    dest = int(user_input[1])

    return source, dest


def play_level(num_rings, scores):
    disks, sizes, pegs = make_level(num_rings)
    optimal = (2 ** num_rings) - 1
    move_count = 0
    start_time = time.perf_counter()

    print(f"\nTower of Hanoi - Level {num_rings}")
    print(f"Rings: {num_rings}")
    print(f"Optimal moves: {optimal}")
    print("Enter moves like: 13, 32, 21")
    print("Type 'end' or 'e' to quit after this level, or press Ctrl+C anytime.")

    while True:
        print_pegs(pegs, move_count, num_rings)

        if is_solved(pegs, num_rings):
            elapsed = time.perf_counter() - start_time
            difference = move_count - optimal

            print(f"\nSolved Level {num_rings}!")
            print(f"Moves: {move_count}")
            print(f"Optimal: {optimal}")
            print(f"Off by: {difference}")
            print(f"Time: {elapsed:.2f} seconds")

            message = update_score(scores, num_rings, move_count, elapsed)
            save_scores(scores)

            print(message)

            best = scores[str(num_rings)]
            print(f"Best for Level {num_rings}: {best['moves']} moves, {best['time']} seconds")

            if move_count != optimal:
                print("\nYou must solve the level in the optimal number of moves to unlock the next level.")
                return False

            choice = input("\nPerfect solve! Press Enter for next level, or type 'end'/'e' to quit: ").strip().lower()
            if choice in ["end", "e"]:
                return False

            return True

        user_input = input("Enter move: ")
        src, dst = parse_move(user_input)

        if src == "end":
            return False

        if src is None:
            print("Invalid format. Use moves like: 13, 32, or 2 1")
            continue

        if src not in pegs or dst not in pegs:
            print("Invalid pegs. Use 1, 2, or 3.")
            continue

        if src == dst:
            print("Invalid move. Source and destination cannot be the same.")
            continue

        if not is_valid_move(pegs, sizes, src, dst):
            print("Invalid move! Cannot place larger disk on smaller one.")
            continue

        move_disk(pegs, src, dst)
        move_count += 1


def main():
    scores = load_scores()
    start_level = choose_starting_level(scores)

    for level in range(start_level, MAX_RINGS + 1):
        keep_playing = play_level(level, scores)

        if not keep_playing:
            print("\nExited safely.")
            break
    else:
        print("\nYou completed all levels!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExited safely.")