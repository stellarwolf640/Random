NUM_RINGS = 10  # Change to any number you want


def generate_disks(n):
    """Generate disk labels A, B, C... AA, AB... if needed."""
    labels = []
    i = 0
    while len(labels) < n:
        label = ""
        x = i
        while True:
            label = chr(ord('A') + (x % 26)) + label
            x = x // 26 - 1
            if x < 0:
                break
        labels.append(label)
        i += 1
    return labels


def print_pegs(pegs):
    max_height = max(len(peg) for peg in pegs.values())

    for i in range(max_height - 1, -1, -1):
        row = []
        for peg in ['A', 'B', 'C']:
            if i < len(pegs[peg]):
                row.append(f"{pegs[peg][i]:>3}")
            else:
                row.append("  |")
        print(" ".join(row))

    print(" A   B   C")
    print("-" * 15)


def hanoi_visual(n, source, auxiliary, destination, pegs, step=[1]):
    if n == 1:
        disk = pegs[source].pop()
        pegs[destination].append(disk)
        print(f"Step {step[0]}: Move {disk} from {source} → {destination}")
        print_pegs(pegs)
        step[0] += 1
    else:
        hanoi_visual(n - 1, source, destination, auxiliary, pegs, step)

        disk = pegs[source].pop()
        pegs[destination].append(disk)
        print(f"Step {step[0]}: Move {disk} from {source} → {destination}")
        print_pegs(pegs)
        step[0] += 1

        hanoi_visual(n - 1, auxiliary, source, destination, pegs, step)


# Generate starting stack (largest at bottom)
disks = generate_disks(NUM_RINGS)

pegs = {
    'A': disks[::-1],   # Reverse so largest is on the bottom
    'B': [],
    'C': []
}

print("Initial State:")
print_pegs(pegs)

hanoi_visual(NUM_RINGS, 'A', 'B', 'C', pegs)