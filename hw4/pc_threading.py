#!/usr/bin/env python3
# CISC 3320 - HW4: Producer-Consumer (threading version)
import threading
import time
import random
import argparse
from collections import deque


print_lock = threading.Lock()   # printing is a shared resource too
quiet = False


def log(msg):
    if not quiet:
        with print_lock:
            print(msg, flush=True)


def do_work(kind, consumer=False):
    # simulated work for making / processing one item
    if kind == "io":
        low, high = (0.03, 0.08) if consumer else (0.01, 0.03)   # consumers are slower
        time.sleep(random.uniform(low, high))      # waiting (GIL is released)
    else:
        total = 0
        for i in range(300_000):                    # heavy math (GIL is held)
            total += i * i


class BoundedBuffer:
    # a monitor: the data + one lock + two condition variables
    def __init__(self, capacity):
        self.capacity = capacity
        self.items = deque()
        self.lock = threading.Lock()                 # only one thread touches items at a time
        self.not_full = threading.Condition(self.lock)    # producers wait here
        self.not_empty = threading.Condition(self.lock)   # consumers wait here

    def put(self, item, who, label=None):
        # label is the text for the "produced" line (None = say nothing, used for stop pills)
        with self.not_full:
            waited = False
            while len(self.items) >= self.capacity:   # while, never if
                if not waited:
                    log(f"[{who}] buffer full - waiting")
                    waited = True
                self.not_full.wait()
            if waited:
                log(f"[{who}] resumed")
            self.items.append(item)
            if label:
                # printed inside the lock on purpose: keeps the log in true order
                log(f"{'[' + who + '] ' + label:<50}buffer size: {len(self.items)}")
            self.not_empty.notify()                   # wake one consumer

    def get(self, who):
        with self.not_empty:
            waited = False
            while len(self.items) == 0:
                if not waited:
                    log(f"[{who}] buffer empty - waiting")
                    waited = True
                self.not_empty.wait()
            if waited:
                log(f"[{who}] resumed")
            item = self.items.popleft()
            if item is not None:
                pid, n = item
                msg = f"[{who}] consumed item {n} from producer {pid}"
                log(f"{msg:<50}buffer size: {len(self.items)}")
            self.not_full.notify()                    # wake one producer
            return item


def producer(pid, buf, num_items, work):
    who = f"producer {pid}"
    for n in range(num_items):
        do_work(work)                                 # make the item (outside the lock)
        buf.put((pid, n), who, f"produced item {n}")


def consumer(cid, buf, work, results):
    who = f"consumer {cid}"
    while True:
        item = buf.get(who)
        if item is None:                              # stop pill
            log(f"[{who}] received stop signal - exiting")
            return
        do_work(work, consumer=True)                  # process the item (outside the lock)
        results[cid - 1].append(item)                 # each consumer writes only its own list


def main():
    global quiet
    parser = argparse.ArgumentParser(description="Producer-consumer with threading")
    parser.add_argument("--producers", type=int, default=2)
    parser.add_argument("--consumers", type=int, default=2)
    parser.add_argument("--capacity", type=int, default=3, help="buffer size")
    parser.add_argument("--items", type=int, default=5, help="items made by EACH producer")
    parser.add_argument("--work", choices=["io", "cpu"], default="io")
    parser.add_argument("--quiet", action="store_true", help="only print the summary (for timing)")
    args = parser.parse_args()
    if min(args.producers, args.consumers, args.capacity, args.items) < 1:
        parser.error("all numbers must be at least 1")
    quiet = args.quiet

    buf = BoundedBuffer(args.capacity)
    results = [[] for _ in range(args.consumers)]

    producers = [threading.Thread(target=producer, args=(i, buf, args.items, args.work))
                 for i in range(1, args.producers + 1)]
    consumers = [threading.Thread(target=consumer, args=(i, buf, args.work, results))
                 for i in range(1, args.consumers + 1)]

    start = time.perf_counter()
    for t in producers + consumers:
        t.start()

    for t in producers:
        t.join()                                      # wait until every item has been made
    for _ in consumers:
        buf.put(None, "main")                         # one stop pill PER consumer
    for t in consumers:
        t.join()
    elapsed = time.perf_counter() - start

    consumed = [item for lst in results for item in lst]
    expected = {(p, n) for p in range(1, args.producers + 1) for n in range(args.items)}
    exactly_once = len(consumed) == len(expected) and set(consumed) == expected

    print(f"all producers finished, all consumers finished, {len(buf.items)} items left")
    print(f"produced {len(expected)}, consumed {len(consumed)}, each item consumed exactly once: "
          f"{'yes' if exactly_once else 'NO'}")
    print(f"elapsed (threading, {args.work}): {elapsed:.3f} s")


if __name__ == "__main__":
    main()
