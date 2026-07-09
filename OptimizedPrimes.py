import math

LIMIT = 10_000_000_000

_MILLER_RABIN_BASES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def prime_count(limit):
    if limit < 2:
        return 0

    root = math.isqrt(limit)
    values = [limit // i for i in range(1, root + 1)]
    values += list(range(values[-1] - 1, 0, -1))
    counts = {value: value - 1 for value in values}

    for prime in range(2, root + 1):
        if counts[prime] == counts[prime - 1]:
            continue

        previous_prime_count = counts[prime - 1]
        prime_squared = prime * prime

        for value in values:
            if value < prime_squared:
                break
            counts[value] -= counts[value // prime] - previous_prime_count

    return counts[limit]


def is_prime(number):
    if number < 2:
        return False

    for prime in _MILLER_RABIN_BASES:
        if number == prime:
            return True
        if number % prime == 0:
            return False

    odd_part = number - 1
    power_of_two = 0

    while odd_part % 2 == 0:
        power_of_two += 1
        odd_part //= 2

    for base in _MILLER_RABIN_BASES:
        if base >= number:
            continue

        result = pow(base, odd_part, number)
        if result == 1 or result == number - 1:
            continue

        for _ in range(power_of_two - 1):
            result = (result * result) % number
            if result == number - 1:
                break
        else:
            return False

    return True


def largest_prime_at_most(limit):
    if limit < 2:
        return None
    if limit == 2:
        return 2

    candidate = limit if limit % 2 else limit - 1

    while candidate >= 3:
        if is_prime(candidate):
            return candidate
        candidate -= 2

    return 2


def find_prime_stats(limit):
    return prime_count(limit), largest_prime_at_most(limit)


def print_prime_stats(limit):
    prime_total, largest_prime = find_prime_stats(limit)
    largest_prime_text = "None" if largest_prime is None else f"{largest_prime:,}"

    print(f"Prime Count: {prime_total:,}")
    print(f"Largest Prime: {largest_prime_text}")


if __name__ == "__main__":
    print_prime_stats(LIMIT)
