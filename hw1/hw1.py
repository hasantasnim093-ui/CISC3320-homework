#!/usr/bin/env python3
# CISC 3320 - HW1: Process Inspection Script
import os


def main():
    # PID and PPID (two real syscalls)
    print("PID:", os.getpid())
    print("PPID:", os.getppid())

    # Environment variables
    print("\nEnvironment variables:")
    for key, value in os.environ.items():
        print(f"{key}={value}")

    # Open file descriptors, listed from /proc/self/fd
    print("\nOpen file descriptors:")
    try:
        for fd in os.listdir("/proc/self/fd"):
            print(fd)
    except OSError as e:
        print("Could not read /proc/self/fd:", e)


if __name__ == "__main__":
    main()
