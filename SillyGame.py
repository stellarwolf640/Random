import random
import time
import os

system_roots = [
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\Windows\WinSxS",
    r"C:\Windows\System32\drivers",
    r"C:\Windows\System32\config",
    r"C:\Windows\System32\wbem",
    r"C:\Windows\System32\spool",
]

subfolders = [
    "drivers", "config", "catroot", "catroot2", "LogFiles", "Recovery",
    "Migration", "CodeIntegrity", "Tasks", "GroupPolicy", "DriverStore",
    "FileRepository", "en-US", "winevt", "Security", "PolicyDefinitions",
    "WindowsPowerShell", "NetworkList", "SystemProfile", "SRU", "wbem",
    "Performance", "Boot", "UMDF", "WDI", "Diagnostics", "Crypto",
    "Protect", "MachineKeys", "SoftwareDistribution"
]

file_bases = [
    "kernel32", "user32", "ntoskrnl", "hal", "winload", "bootres",
    "shell32", "advapi32", "crypt32", "sechost", "lsass", "smss",
    "csrss", "wininit", "services", "svchost", "dwm", "explorer",
    "registry", "security", "system", "software", "sam", "default",
    "bootmgr", "bcd", "netlogon", "gdi32", "setupapi", "ntdll"
]

extensions = [
    ".dll", ".exe", ".sys", ".dat", ".log", ".mui", ".manifest",
    ".cat", ".ini", ".bak", ".bin", ".evtx", ".pol"
]

status_messages = [
    "Bypassing permissions...",
    "Escalating privileges...",
    "Indexing protected directories...",
    "Corrupting Defender...",
    "Requesting admin token...",
    "Overriding safeguards...",
]

def fake_path():
    root = random.choice(system_roots)
    depth = random.randint(1, 10)
    nested = "\\".join(random.choice(subfolders) for _ in range(depth))
    filename = random.choice(file_bases) + random.choice(extensions)

    if random.random() < 0.35:
        filename = f"{random.choice(file_bases)}_{random.randint(1000, 9999)}{random.choice(extensions)}"

    return f"{root}\\{nested}\\{filename}"

secret_number = random.randint(1, 10)

os.system('cls')

try:
    print("Silly Guessing Game!")
    user_guess = int(input("Guess a number 1-10: "))
except ValueError:
    print("Invalid input.")
    raise SystemExit

try:
    if user_guess == secret_number:
        print("Congrats! You win!")
    else:
        print("Wrong answer.")
        time.sleep(0.8)
        print("Punishment Time!")
        time.sleep(2)
        print("Initializing System32 deletion protocol...")
        time.sleep(0.8)

        for message in status_messages[:4]:
            print(message)
            time.sleep(0.4)

        total = 6500

        for i in range(1, total + 1):
            action = "Deleting"

            print(f"{action}: {fake_path()}")

            time.sleep(random.uniform(0.0001, 0.002))

        time.sleep(1.5)
        print("\nDeletion failed successfully.")
except KeyboardInterrupt:
    print("You think you can stop this?")
    time.sleep(1.5)
    total = 150

    for i in range(1, total + 1):
        action = random.choice([
            "Deleting",
            "Removing",
            "Purging",
            "Overwriting",
            "Unlinking",
            "Destroying",
            "Wiping"
        ])

        action = "Deleting"

        print(f"{action}: {fake_path()}")

        if i % random.randint(18, 30) == 0:
            print(f"WARNING: {random.choice(status_messages)}")

        time.sleep(random.uniform(0.005, 0.025))

    time.sleep(3)
    print("\nDeletion failed successfully.")

