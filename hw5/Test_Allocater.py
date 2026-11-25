#!/usr/bin/env python3
# CISC 3320 - HW5: tests for allocator.py
# usage: python3 test_allocator.py
# (the allocator also asserts its own invariants after every alloc/free)
import random
import sys
from allocator import Allocator, AllocError

failures = 0


def check(cond, msg):
    global failures
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        failures += 1


def fails(a, fn, *args):
    # True if the call raised AllocError
    try:
        fn(*args)
    except AllocError:
        return True
    return False


def holes(a):
    return a.stats()["free_list"]


# ---------- 1. the nine-step trace from Lecture 10 ----------
def run_trace(policy):
    a = Allocator(1000, policy)
    placed = {}
    steps = []                                   # free list after each step
    for name, size in [("A", 200), ("B", 300), ("C", 150), ("D", 100)]:
        placed[name] = a.alloc(name, size)
        steps.append(holes(a))
    a.free("B"); steps.append(holes(a))
    a.free("D"); steps.append(holes(a))
    placed["E"] = a.alloc("E", 280); steps.append(holes(a))
    placed["F"] = a.alloc("F", 100); steps.append(holes(a))
    g_failed = fails(a, a.alloc, "G", 260); steps.append(holes(a))
    return a, placed, steps, g_failed


print("== trace ==")
# first-fit, all nine steps (slide: trace table)
a, placed, steps, g_failed = run_trace("first")
expected = [
    [(200, 1000)], [(500, 1000)], [(650, 1000)], [(750, 1000)],
    [(200, 500), (750, 1000)], [(200, 500), (650, 1000)],
    [(480, 500), (650, 1000)], [(480, 500), (750, 1000)], [(480, 500), (750, 1000)],
]
check(steps == expected, "first-fit: free list matches the slide after every one of the 9 steps")
check(placed["E"] == 200 and placed["F"] == 650 and g_failed, "first-fit: E at 200, F at 650, G fails")

# the three-policy comparison (slide: same workload, three policies)
for policy, e_at, f_at, end_holes in [
    ("first", 200, 650, [(480, 500), (750, 1000)]),
    ("best", 200, 650, [(480, 500), (750, 1000)]),
    ("worst", 650, 200, [(300, 500), (930, 1000)]),
]:
    a, placed, steps, g_failed = run_trace(policy)
    check(placed["E"] == e_at and placed["F"] == f_at and holes(a) == end_holes and g_failed,
          f"{policy}-fit: E at {e_at}, F at {f_at}, holes {end_holes}, G fails")
    check(a.stats()["free"] == 270,
          f"{policy}-fit: 270 free in total, yet G (260) cannot fit (external fragmentation)")

# ---------- 2. exact fit ----------
print("== exact fit ==")
a = Allocator(100)
a.alloc("A", 40); a.alloc("B", 20); a.alloc("C", 40)
a.free("B")
a.alloc("D", 20)                                 # exactly the size of the hole
check(a.stats()["holes"] == 0, "exact fit: the hole disappears")
check(all(size > 0 for _, _, size, _ in a.blocks_list()), "exact fit: no zero-length block")

# ---------- 3. coalescing ----------
print("== coalescing ==")
a = Allocator(1000)
for n in "ABCD":
    a.alloc(n, 100)
a.free("A"); a.free("C")
check(holes(a) == [(0, 100), (200, 300), (400, 1000)], "two separate holes before the middle free")
a.free("B")                                      # touches a hole on BOTH sides
check(holes(a) == [(0, 300), (400, 1000)], "free between two holes merges all three into one")
a.free("D")
check(holes(a) == [(0, 1000)], "free everything -> one hole of the full pool size")

for policy in ("first", "best", "worst"):
    a, placed, _, _ = run_trace(policy)
    for name in placed:
        if name not in ("B", "D"):               # B and D were already freed in the trace
            a.free(name)
    check(holes(a) == [(0, 1000)], f"{policy}-fit: after the trace, freeing everything gives one full hole")

# ---------- 4. tie-breaks ----------
print("== tie-breaks ==")
for policy in ("best", "worst"):
    a = Allocator(500, policy)
    for n in "ABCDE":
        a.alloc(n, 100)
    a.free("B"); a.free("D")                     # two equal holes: [100-200) and [300-400)
    check(a.alloc("F", 50) == 100, f"{policy}-fit: equal holes -> lowest address wins")

# ---------- 5. failures leave the pool unchanged ----------
print("== failure cases ==")
a = Allocator(1000)
a.alloc("A", 200); a.alloc("B", 100); a.free("B")
before = (a.blocks_list(), a.stats())
cases = [
    ("oversized request", a.alloc, "X", 5000),
    ("request bigger than largest hole", a.alloc, "X", 801),
    ("zero size", a.alloc, "X", 0),
    ("negative size", a.alloc, "X", -5),
    ("duplicate name", a.alloc, "A", 10),
    ("unknown name", a.free, "nope"),
    ("double free", a.free, "B"),
]
for label, fn, *args in cases:
    check(fails(a, fn, *args) and (a.blocks_list(), a.stats()) == before,
          f"{label}: error raised, pool unchanged")
try:
    a.free("B")
except AllocError as e:
    check("double free" in str(e), "double free gets its own message")
try:
    a.free("nope")
except AllocError as e:
    check("unknown name" in str(e), "unknown name gets its own message")

# a freed name can be used again
a.alloc("B", 50)
check(a.free("B") is not None, "a freed name can be allocated again")

# ---------- 6. stats ----------
print("== stats ==")
a = Allocator(1000)
a.alloc("A", 200); a.alloc("B", 300); a.alloc("C", 150); a.free("B")
s = a.stats()
check((s["used"], s["free"], s["holes"], s["largest_hole"]) == (350, 650, 2, 350), "used/free/holes/largest")
check(round(s["fragmentation"], 1) == 46.2, "fragmentation = 1 - 350/650 = 46.2%")
full = Allocator(100); full.alloc("A", 100)
check(full.stats()["fragmentation"] == 0.0, "no free space -> 0% (no divide by zero)")

# ---------- 7. random stress (invariants are asserted inside every operation) ----------
print("== random stress ==")
for policy in ("first", "best", "worst"):
    rnd = random.Random(42)
    a = Allocator(1000, policy)
    live, counter = [], 0
    for _ in range(3000):
        if live and rnd.random() < 0.5:
            a.free(live.pop(rnd.randrange(len(live))))
        else:
            counter += 1
            name = f"p{counter}"
            try:
                a.alloc(name, rnd.randint(1, 120))
                live.append(name)
            except AllocError:
                pass
    for name in live:
        a.free(name)
    check(holes(a) == [(0, 1000)], f"{policy}-fit: 3000 random operations, then free all -> one full hole")

print()
if failures:
    print(f"{failures} test(s) FAILED")
    sys.exit(1)
print("all tests passed")
