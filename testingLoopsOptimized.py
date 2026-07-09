import math
import re
import shutil
import subprocess
import time

#N = 10_000_000_000
#N = 10_000_000_000_000_000_000
N = 100000000

DIVISOR_MAX_N = 10_000_000
SIEVE_MAX_N = 500_000_000
OPTIMIZED_SIEVE_MAX_N = 5_000_000_000
PRIME_COUNTING_MAX_N = 500_000_000_000

_MILLER_RABIN_BASES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


class MethodUnavailable(Exception):
    pass


def primeCountingMethod(N):
    if N < 2:
        return 0, None

    root = math.isqrt(N)
    values = [N // i for i in range(1, root + 1)]
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

    return counts[N], largestPrimeAtMost(N)


def primecountLibraryMethod(N):
    if N < 2:
        return 0, None

    try:
        import primecountpy as primecount
    except ImportError:
        primecount = None

    if primecount is not None:
        return primecount.prime_pi(N), largestPrimeAtMost(N)

    if shutil.which("primecount") is None:
        raise MethodUnavailable(
            "Install primecountpy or the primecount command-line tool"
        )

    result = subprocess.run(
        ["primecount", str(N)],
        capture_output=True,
        check=True,
        text=True,
    )
    counts = re.findall(r"\d[\d,]*", result.stdout)

    if not counts:
        raise MethodUnavailable("primecount did not return a usable count")

    return int(counts[-1].replace(",", "")), largestPrimeAtMost(N)


def isPrime(N):
    if N < 2:
        return False

    for prime in _MILLER_RABIN_BASES:
        if N == prime:
            return True
        if N % prime == 0:
            return False

    odd_part = N - 1
    power_of_two = 0

    while odd_part % 2 == 0:
        power_of_two += 1
        odd_part //= 2

    for base in _MILLER_RABIN_BASES:
        if base >= N:
            continue

        result = pow(base, odd_part, N)
        if result == 1 or result == N - 1:
            continue

        for _ in range(power_of_two - 1):
            result = (result * result) % N
            if result == N - 1:
                break
        else:
            return False

    return True


def largestPrimeAtMost(N):
    if N < 2:
        return None
    if N == 2:
        return 2

    candidate = N if N % 2 else N - 1

    while candidate >= 3:
        if isPrime(candidate):
            return candidate
        candidate -= 2

    return 2


def sieveOptimized(N):
    if N < 2:
        return 0, None

    # Each index represents an odd number:
    # index 0 = 1, index 1 = 3, index 2 = 5, etc.
    odd_count = (N + 1) // 2
    sieve = bytearray(b"\x01") * odd_count

    # 1 is not prime.
    sieve[0] = 0

    # Only need to mark multiples using primes up to sqrt(limit).
    for prime in range(3, math.isqrt(N) + 1, 2):
        if sieve[prime // 2]:
            start = (prime * prime) // 2

            # Mark odd multiples of this prime as non-prime.
            sieve[start::prime] = b"\x00" * (
                ((odd_count - start - 1) // prime) + 1
            )

    # Add 1 because 2 is prime but is not represented in the odd-only sieve.
    prime_count = 1 + sieve.count(1)

    last_prime_index = sieve.rfind(1)
    largest_prime = 2 if last_prime_index < 1 else (last_prime_index * 2) + 1

    return prime_count, largest_prime

def divisorMethod(N):
    if N < 2:
        return 0, None

    primes = [2]
    lprime = 2

    # No need to test even candidates after 2.
    for j in range(3, N + 1, 2):
        is_prime = True

        for i in primes:
            # Once i is above sqrt(j), no later prime can divide j.
            if i * i > j:
                break

            if j % i == 0:
                is_prime = False
                break

        if is_prime:
            primes.append(j)
            lprime = j
    return len(primes), lprime

def sieveMethod(N):
    if N < 2:
        return 0, None

    # bytearray uses much less memory than a list of Python booleans.
    # 0 = not marked composite, 1 = composite
    sieve = bytearray(N + 1)

    sieve[0] = 1
    sieve[1] = 1

    # Only primes up through sqrt(N) need to mark multiples.
    limit = math.isqrt(N)

    for j in range(2, limit + 1):
        if not sieve[j]:
            # Start at j * j, since smaller multiples were handled earlier.
            for multiple in range(j * j, N + 1, j):
                sieve[multiple] = 1

    pcount = 0
    bprime = 2

    # Count remaining unmarked values after the sieve is built.
    for j in range(2, N + 1):
        if not sieve[j]:
            pcount += 1
            bprime = j
    return pcount, bprime


def primeText(prime):
    return "None" if prime is None else f"{prime:,}"


def runMethod(methodName, method, maxN=None):
    print(f"\n\n{methodName}:")

    if maxN is not None and N > maxN:
        print(f"Skipped: N is greater than {maxN:,}")
        return None

    start_time = time.perf_counter()
    try:
        primeCount, largestPrime = method(N)
    except MethodUnavailable as e:
        print(f"Skipped: {e}")
        return None
    end_time = time.perf_counter()
    elapsed = end_time - start_time

    print(f"Prime Count: {primeCount:,}")
    print(f"Largest Prime: {primeText(largestPrime)}")
    print(f"Elapsed Time: {elapsed:.6f} seconds")

    return methodName, primeCount, largestPrime, elapsed


def printSummary(results):
    completedResults = [result for result in results if result is not None]

    if len(completedResults) < 2:
        return

    expectedCount = completedResults[0][1]
    expectedLargest = completedResults[0][2]
    resultsMatch = all(
        primeCount == expectedCount and largestPrime == expectedLargest
        for _, primeCount, largestPrime, _ in completedResults
    )
    fastestMethod = min(completedResults, key=lambda result: result[3])

    print("\n\nSummary:")
    print(f"Completed Methods: {len(completedResults)}")
    print(f"Results Match: {'Yes' if resultsMatch else 'No'}")
    print(f"Fastest Method: {fastestMethod[0]} ({fastestMethod[3]:.6f} seconds)")


def main():
    print(f"Limit: {N:,}")

    results = [
        runMethod("Divisor Method", divisorMethod, DIVISOR_MAX_N),
        runMethod("Sieve Method", sieveMethod, SIEVE_MAX_N),
        runMethod("Optimized Sieve Method", sieveOptimized, OPTIMIZED_SIEVE_MAX_N),
        runMethod("Prime Counting Method", primeCountingMethod, PRIME_COUNTING_MAX_N),
        runMethod("Primecount Library Method", primecountLibraryMethod),
    ]

    printSummary(results)


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("\nInterrupted by User")

    except Exception as e:
        print(e)
