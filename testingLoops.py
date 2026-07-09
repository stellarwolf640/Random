import time

Nprime = False

N = 5_000_000

sieve = [False] * N

try:
    start_time = time.perf_counter()
    primes = [2, 3]
    lprime = 3

    
    for j in range(5, N + 1, 2):
        for i in primes:
            if j % i == 0:
                Nprime = True
                break
            if i * i > j:
                break

        if not Nprime:
            primes.append(j)
            lprime = j

        Nprime = False

    end_time = time.perf_counter()

    # Write primes to file
    # with open("prime-list.txt", "w") as f:
    #     f.write(str(primes))

    print("Prime Count: " + str(len(primes)))
    print("Largest Prime: " + str(lprime))

    # print("Primes saved to 'prime-list.txt'")
    print(f"Divisor time Elapsed {end_time - start_time}")

    start_time = time.perf_counter()

    bprime = 3
    pcount = 0

    for j in range(len(sieve)):
        if j == 0 or j == 1:
            sieve[j] = True
        else:
            if not sieve[j]:
                bprime = j
                pcount = pcount + 1
                up = j
                i = 1

                while up < N:
                    sieve[j * i] = True
                    i = i + 1
                    up = j * i

    end_time = time.perf_counter()

    print("Prime Count: " + str(pcount))
    print("Largest Prime: " + str(bprime))
    
    print(f"Sieve time Elapsed {end_time - start_time}")
    

except KeyboardInterrupt:
    print("\nInterrupted by User")
    end_time = time.perf_counter()
    print(f"Time Elapsed {end_time - start_time}")

except Exception as e:
    print(e)
    end_time = time.perf_counter()
    print(f"Time Elapsed {end_time - start_time}")
