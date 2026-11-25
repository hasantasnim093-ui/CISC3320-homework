#!/usr/bin/env python3
# CISC 3320 - HW5: Memory Allocator Simulator
#
# The Allocator class is a clean module (no printing) so it can drop into PyShell OS.
# The command loop at the bottom is the only part that prints.
import argparse
import threading


POLICIES = {"first": "first-fit", "best": "best-fit", "worst": "worst-fit"}


class AllocError(Exception):
    # every user-facing failure (out of memory, unknown name, double free, ...)
    pass


class Block:
    def __init__(self, start, size, name=None):
        self.start = start
        self.size = size
        self.name = name          # None means this block is a hole (free)

    @property
    def end(self):
        return self.start + self.size


class Allocator:
    # Representation: ONE list of blocks, sorted by address, that always covers
    # the whole pool with no gaps. Holes are blocks whose name is None.
    # So "neighbors" are just the entries before and after in the list.
    def __init__(self, size=1000, policy="first"):
        if size <= 0:
            raise AllocError("pool size must be positive")
        self._lock = threading.Lock()        # the pool is shared between jobs in PyShell
        self.pool_size = size
        self.policy = "first"
        self.set_policy(policy)
        self.blocks = [Block(0, size)]       # at the start: one big hole
        self.freed_names = set()             # lets us tell "double free" from "unknown name"

    # ---------- public functions (they return results, never print) ----------

    def set_policy(self, policy):
        key = policy.lower().replace("-fit", "")
        if key not in POLICIES:
            raise AllocError(f"unknown policy '{policy}' (use first, best or worst)")
        with self._lock:
            self.policy = key
        return POLICIES[key]

    def alloc(self, name, size):
        # returns the start address of the new block
        with self._lock:
            if not isinstance(size, int) or size <= 0:
                raise AllocError("size must be a positive whole number")
            if self._find(name) is not None:
                raise AllocError(f"name '{name}' is already allocated")
            hole = self._pick_hole(size)
            if hole is None:
                raise AllocError(f"out of memory: need {size}, largest hole is {self._largest()}")

            start = hole.start
            if hole.size == size:
                hole.name = name             # exact fit: the hole BECOMES the block (no 0-size leftover)
            else:
                # split: new block takes the front, the hole keeps the remainder
                self.blocks.insert(self.blocks.index(hole), Block(start, size, name))
                hole.start += size
                hole.size -= size
            self.freed_names.discard(name)
            self._check()
            return start

    def free(self, name):
        # returns (start, size) of the hole this free produced, after merging
        with self._lock:
            block = self._find(name)
            if block is None:
                if name in self.freed_names:
                    raise AllocError(f"double free: '{name}' was already freed")
                raise AllocError(f"unknown name '{name}'")
            block.name = None
            self.freed_names.add(name)

            i = self.blocks.index(block)
            if i + 1 < len(self.blocks) and self.blocks[i + 1].name is None:
                block.size += self.blocks[i + 1].size      # merge with the hole after
                del self.blocks[i + 1]
            if i > 0 and self.blocks[i - 1].name is None:
                before = self.blocks[i - 1]
                before.size += block.size                  # merge with the hole before
                del self.blocks[i]
                block = before
            self._check()
            return block.start, block.size

    def stats(self):
        with self._lock:
            holes = [b for b in self.blocks if b.name is None]
            used = sum(b.size for b in self.blocks if b.name is not None)
            free = sum(h.size for h in holes)
            largest = self._largest()
            # external fragmentation = 1 - (largest hole / total free), as a percent
            frag = 0.0 if free == 0 else (1 - largest / free) * 100
            return {
                "pool": self.pool_size,
                "used": used,
                "free": free,
                "holes": len(holes),
                "largest_hole": largest,
                "fragmentation": frag,
                "free_list": [(h.start, h.end) for h in holes],
            }

    def blocks_list(self):
        # every block in address order: (start, end, size, name or None)
        with self._lock:
            return [(b.start, b.end, b.size, b.name) for b in self.blocks]

    # ---------- helpers (called with the lock already held) ----------

    def _find(self, name):
        for b in self.blocks:
            if b.name == name:
                return b
        return None

    def _largest(self):
        return max((b.size for b in self.blocks if b.name is None), default=0)

    def _pick_hole(self, size):
        holes = [b for b in self.blocks if b.name is None and b.size >= size]
        if not holes:
            return None
        if self.policy == "first":
            return holes[0]                                        # lowest address that fits
        if self.policy == "best":
            return min(holes, key=lambda b: (b.size, b.start))     # smallest; tie -> lowest address
        return max(holes, key=lambda b: (b.size, -b.start))        # largest; tie -> lowest address

    def _check(self):
        # invariants, checked after every operation
        pos = 0
        prev_was_hole = False
        for b in self.blocks:
            assert b.start == pos, "gap or overlap between blocks"
            assert b.size > 0, "zero-size block"
            is_hole = b.name is None
            assert not (is_hole and prev_was_hole), "two adjacent holes were not merged"
            prev_was_hole = is_hole
            pos = b.end
        assert pos == self.pool_size, "blocks do not cover the pool"
        names = [b.name for b in self.blocks if b.name is not None]
        assert len(names) == len(set(names)), "duplicate name"
        used = sum(b.size for b in self.blocks if b.name is not None)
        free = sum(b.size for b in self.blocks if b.name is None)
        assert used + free == self.pool_size, "used + free != pool size"


# ---------- command loop (all the printing lives here) ----------

def rng(start, end):
    return f"[{start}–{end})"


def show_stats(a):
    s = a.stats()
    print(f"pool {s['pool']}   used {s['used']}   free {s['free']}   holes {s['holes']}")
    print(f"largest hole {s['largest_hole']}   fragmentation {s['fragmentation']:.1f}%")
    holes = " ".join(rng(st, en) for st, en in s["free_list"]) or "(none)"
    print(f"free list: {holes}")


def show_map(a):
    for start, end, size, name in a.blocks_list():
        print(f"{rng(start, end):<14}{size:>5}  {name if name else '(free)'}")


HELP = """commands:
  alloc <name> <size>     allocate a block
  free <name>             free a block
  stats                   used, free, holes, largest hole, fragmentation
  map                     print every block
  policy [first|best|worst]   show or change the placement policy
  help                    this message
  exit                    quit"""


def handle(a, line):
    # returns False when the user wants to quit
    parts = line.split()
    if not parts:
        return True
    cmd, args = parts[0].lower(), parts[1:]

    if cmd in ("exit", "quit"):
        return False
    elif cmd == "help":
        print(HELP)
    elif cmd == "alloc":
        if len(args) != 2:
            print("usage: alloc <name> <size>")
            return True
        try:
            size = int(args[1])
        except ValueError:
            print("error: size must be a positive whole number")
            return True
        try:
            start = a.alloc(args[0], size)
            print(f"{args[0]}: {size} bytes at {rng(start, start + size)}")
        except AllocError as e:
            print(f"error: {e}")
    elif cmd == "free":
        if len(args) != 1:
            print("usage: free <name>")
            return True
        try:
            start, size = a.free(args[0])
            print(f"{args[0]} freed (hole {rng(start, start + size)} {size} bytes)")
        except AllocError as e:
            print(f"error: {e}")
    elif cmd == "stats":
        show_stats(a)
    elif cmd == "map":
        show_map(a)
    elif cmd == "policy":
        if not args:
            print(f"policy: {POLICIES[a.policy]}")
        else:
            try:
                print(f"policy: {a.set_policy(args[0])}")
            except AllocError as e:
                print(f"error: {e}")
    else:
        print(f"unknown command: {cmd} (type help)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Memory allocator simulator")
    parser.add_argument("--size", type=int, default=1000, help="pool size in bytes (default 1000)")
    parser.add_argument("--policy", default="first", help="first, best or worst (default first)")
    args = parser.parse_args()

    try:
        a = Allocator(args.size, args.policy)
    except AllocError as e:
        parser.error(str(e))

    while True:
        try:
            line = input("alloc> ")
        except EOFError:
            print()
            break
        if not handle(a, line):
            break


if __name__ == "__main__":
    main()
