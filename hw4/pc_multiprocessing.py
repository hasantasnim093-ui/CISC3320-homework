#!/usr/bin/env python3
# CISC 3320 - HW4: Producer-Consumer (multiprocessing version)
import multiprocessing as mp
import queue
import time
import random
import argparse


def log(print_lock, quiet, msg):
    # processes do not share memory, so the print lock must be passed in
    if not quiet:
        with print_lock:
            print(msg, flush=True)


def do_work(kind, consumer=False):
    # simulated work for making / processing one item
    if kind == "io":
        low, high = (0.03, 0.08) if consumer else (0.01, 0.03)   # consumers are slower
        time.sleep(random.uniform(low, high))      # waiting
    else:
        total = 0
        for i in range(300_000):                    # heavy math (each process has its own GIL)
            total += i * i


def producer(pid, buf, num_items, work, print_lock, quiet):
    who = f"producer {pid}"
    for n in range(num_items):
        do_work(work)                                 # make the item
        item = (pid, n)
        try:
            buf.put_nowait(item)
        except queue.Full:                            # buffer is full -> block until a slot frees
            log(print_lock, quiet, f"[{who}] buffer full - waiting")
            buf.put(item)
            log(print_lock, quiet, f"[{who}] resumed")
        msg = f"[{who}] produced item {n}"
        log(print_lock, quiet, f"{msg:<50}buffer size: {buf.qsize()}")


def consumer(cid, buf, work, results, print_lock, quiet):
    who = f"consumer {cid}"
    while True:
        try:
            item = buf.get_nowait()
        except queue.Empty:                           # nothing there -> block until an item arrives
            log(print_lock, quiet, f"[{who}] buffer empty - waiting")
            item = buf.get()
            log(print_lock, quiet, f"[{who}] resumed")
        if item is None:                              # stop pill
            log(print_lock, quiet, f"[{who}] received stop signal - exiting")
            return
        pid, n = item
        msg = f"[{who}] consumed item {n} from producer {pid}"
        log(print_lock, quiet, f"{msg:<50}buffer size: {buf.qsize()}")
        do_work(work, consumer=True)                  # process the item
        results.put(item)                             # report it back to main


def main():
    parser = argparse.ArgumentParser(description="Producer-consumer with multiprocessing")
    parser.add_argument("--producers", type=int, default=2)
    parser.add_argument("--consumers", type=int, default=2)
    parser.add_argument("--capacity", type=int, default=3, help="buffer size")
    parser.add_argument("--items", type=int, default=5, help="items made by EACH producer")
    parser.add_argument("--work", choices=["io", "cpu"], default="io")
    parser.add_argument("--quiet", action="store_true", help="only print the summary (for timing)")
    args = parser.parse_args()
    if min(args.producers, args.consumers, args.capacity, args.items) < 1:
        parser.error("all numbers must be at least 1")

    buf = mp.Queue(maxsize=args.capacity)             # the bounded buffer (process-safe)
    results = mp.Queue()                              # consumed items, for the final check
    print_lock = mp.Lock()

    producers = [mp.Process(target=producer,
                            args=(i, buf, args.items, args.work, print_lock, args.quiet))
                 for i in range(1, args.producers + 1)]
    consumers = [mp.Process(target=consumer,
                            args=(i, buf, args.work, results, print_lock, args.quiet))
                 for i in range(1, args.consumers + 1)]

    start = time.perf_counter()
    for p in producers + consumers:
        p.start()

    for p in producers:
        p.join()                                      # wait until every item has been made
    for _ in consumers:
        buf.put(None)                                 # one stop pill PER consumer

    total = args.producers * args.items
    consumed = []
    for _ in range(total):                            # read results BEFORE joining consumers
        consumed.append(results.get(timeout=60))
    for p in consumers:
        p.join()
    elapsed = time.perf_counter() - start

    expected = {(p, n) for p in range(1, args.producers + 1) for n in range(args.items)}
    exactly_once = len(consumed) == len(expected) and set(consumed) == expected
    leftover = len(mp.active_children())

    print(f"all producers finished, all consumers finished, {leftover} processes still running")
    print(f"produced {len(expected)}, consumed {len(consumed)}, each item consumed exactly once: "
          f"{'yes' if exactly_once else 'NO'}")
    print(f"elapsed (multiprocessing, {args.work}): {elapsed:.3f} s")


if __name__ == "__main__":
    main()
