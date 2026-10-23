#!/usr/bin/env python3
# CISC 3320 - HW3: Scheduler Simulator
import sys
import copy
import argparse
from collections import deque


# ---------- design settings (all explained in report.md) ----------
DEFAULT_QUANTUM = 4         # round robin quantum
AGING_INTERVAL = 5          # priority: every 5 time units waited = 1 level better
MLFQ_QUANTA = [4, 8, 16]    # Q0, Q1, Q2 (index 0 = highest priority)
BOOST_INTERVAL = 50         # mlfq: every 50 time units everyone goes back to Q0


class SimProcess:
    def __init__(self, pid, arrival_time, burst_time, priority=0):
        self.pid = pid
        self.arrival_time = arrival_time
        self.burst_time = burst_time
        self.remaining_time = burst_time   # shrinks under RR/MLFQ
        self.priority = priority
        self.start_time = None             # first time it got the CPU
        self.completion_time = None


# ---------- reading the workload ----------
def load_workload(path):
    # one row per process: pid,arrival,burst,priority  (priority is optional)
    processes = []
    try:
        with open(path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [x.strip() for x in line.split(",")]
                try:
                    pid = parts[0]
                    arrival = int(parts[1])
                    burst = int(parts[2])
                    priority = int(parts[3]) if len(parts) > 3 else 0
                    if arrival < 0 or burst <= 0:
                        raise ValueError
                except (IndexError, ValueError):
                    print(f"simulator: {path}: bad line {line_num}: {line}")
                    sys.exit(1)
                processes.append(SimProcess(pid, arrival, burst, priority))
    except OSError as e:
        print(f"simulator: {path}: {e.strerror}")
        sys.exit(1)
    if not processes:
        print(f"simulator: {path}: no processes found")
        sys.exit(1)
    return processes


# ---------- the five algorithms ----------
# every one has the same shape: schedule(processes, quantum=None)
# and returns a list of (pid, start, end) segments in time order.

def fcfs_schedule(processes, quantum=None):
    segments = []
    time = 0
    # sorted() is stable, so equal arrival times keep the order from the file
    for p in sorted(processes, key=lambda p: p.arrival_time):
        time = max(time, p.arrival_time)      # CPU sits idle until it arrives
        segments.append((p.pid, time, time + p.burst_time))
        time += p.burst_time
        p.remaining_time = 0
    return segments


def sjf_schedule(processes, quantum=None):
    # non-preemptive: when the CPU frees up, run the shortest ready job
    segments = []
    time = 0
    waiting = list(processes)
    while waiting:
        ready = [p for p in waiting if p.arrival_time <= time]
        if not ready:
            time = min(p.arrival_time for p in waiting)   # idle, jump ahead
            continue
        # tie-break: shorter burst, then earlier arrival, then file order
        p = min(ready, key=lambda p: (p.burst_time, p.arrival_time))
        segments.append((p.pid, time, time + p.burst_time))
        time += p.burst_time
        p.remaining_time = 0
        waiting.remove(p)
    return segments


def round_robin_schedule(processes, quantum=None):
    if quantum is None:
        quantum = DEFAULT_QUANTUM
    segments = []
    pending = sorted(processes, key=lambda p: p.arrival_time)   # not arrived yet
    queue = deque()
    time = 0
    while pending or queue:
        if not queue:
            time = max(time, pending[0].arrival_time)           # idle, jump ahead
        while pending and pending[0].arrival_time <= time:
            queue.append(pending.pop(0))
        p = queue.popleft()
        run = min(quantum, p.remaining_time)
        segments.append((p.pid, time, time + run))
        time += run
        p.remaining_time -= run
        # new arrivals go in line BEFORE the preempted process is re-queued
        while pending and pending[0].arrival_time <= time:
            queue.append(pending.pop(0))
        if p.remaining_time > 0:       # finished exactly at the boundary = not re-queued
            queue.append(p)
    return segments


def effective_priority(p, time):
    # aging: every AGING_INTERVAL units of waiting improves priority by 1
    return p.priority - (time - p.arrival_time) // AGING_INTERVAL


def priority_schedule(processes, quantum=None):
    # non-preemptive, lower number = higher priority
    segments = []
    time = 0
    waiting = list(processes)
    while waiting:
        ready = [p for p in waiting if p.arrival_time <= time]
        if not ready:
            time = min(p.arrival_time for p in waiting)
            continue
        # tie-break: earlier arrival, then whoever is listed first in the file
        p = min(ready, key=lambda p: (effective_priority(p, time), p.arrival_time))
        segments.append((p.pid, time, time + p.burst_time))
        time += p.burst_time
        p.remaining_time = 0
        waiting.remove(p)
    return segments


def admit_arrivals(pending, q0, time):
    # everything that has arrived by 'time' enters the top queue
    while pending and pending[0].arrival_time <= time:
        q0.append(pending.pop(0))


def mlfq_schedule(processes, quantum=None, log=None):
    # 'log' is optional: if given, one (time, pid, queue, action) row is added per slice
    queues = [deque() for _ in MLFQ_QUANTA]
    pending = sorted(processes, key=lambda p: p.arrival_time)
    segments = []
    time = 0
    next_boost = BOOST_INTERVAL
    finished = 0

    while finished < len(processes):
        admit_arrivals(pending, queues[0], time)

        # periodic boost: everyone goes back to the top queue
        if time >= next_boost:
            moved = False
            for q in queues[1:]:
                while q:
                    queues[0].append(q.popleft())
                    moved = True
            if moved and log is not None:
                log.append((time, "-", "-", "Priority boost: everyone back to Q0"))
            while next_boost <= time:
                next_boost += BOOST_INTERVAL

        # pick the front of the highest non-empty queue
        level = None
        for i, q in enumerate(queues):
            if q:
                level = i
                break
        if level is None:
            time = pending[0].arrival_time      # idle, jump ahead
            continue

        p = queues[level].popleft()
        q_size = MLFQ_QUANTA[level]
        run = min(q_size, p.remaining_time)
        start = time
        time += run
        p.remaining_time -= run
        segments.append((p.pid, start, time))
        admit_arrivals(pending, queues[0], time)

        if p.remaining_time == 0:
            finished += 1
            action = f"Finishes at t={time}"
        else:
            # it used its whole quantum and still isn't done -> demote
            new_level = min(level + 1, len(queues) - 1)
            queues[new_level].append(p)
            if new_level == level:
                action = f"Runs full quantum ({q_size}) → stays in Q{level} (bottom)"
            else:
                action = f"Runs full quantum ({q_size}) → demoted to Q{new_level}"
        if log is not None:
            log.append((start, p.pid, f"Q{level}", action))
    return segments


ALGORITHMS = {
    "fcfs":     ("FCFS", fcfs_schedule),
    "sjf":      ("SJF", sjf_schedule),
    "rr":       ("Round Robin", round_robin_schedule),
    "priority": ("Priority", priority_schedule),
    "mlfq":     ("MLFQ", mlfq_schedule),
}


# ---------- metrics (one shared set of formulas for all five) ----------
def compute_metrics(processes, segments):
    for p in processes:
        mine = [(s, e) for pid, s, e in segments if pid == p.pid]
        p.start_time = mine[0][0]           # first time on the CPU
        p.completion_time = mine[-1][1]     # end of its last segment
    results = []
    for p in processes:
        turnaround = p.completion_time - p.arrival_time
        results.append({
            "pid": p.pid,
            "arrival": p.arrival_time,
            "burst": p.burst_time,
            "priority": p.priority,
            "start": p.start_time,
            "completion": p.completion_time,
            "waiting": turnaround - p.burst_time,
            "turnaround": turnaround,
            "response": p.start_time - p.arrival_time,
        })
    results.sort(key=lambda r: r["start"])  # show in the order they first ran
    return results


def averages(results):
    n = len(results)
    return (sum(r["waiting"] for r in results) / n,
            sum(r["turnaround"] for r in results) / n,
            sum(r["response"] for r in results) / n)


def run_algorithm(key, workload, quantum, log=None):
    # fresh copy every time so remaining_time starts clean
    fresh = copy.deepcopy(workload)
    schedule = ALGORITHMS[key][1]
    if key == "mlfq":
        segments = schedule(fresh, quantum, log)
    else:
        segments = schedule(fresh, quantum)
    return compute_metrics(fresh, segments)


# ---------- printing ----------
def print_table(results, show_priority):
    cols = ["PID", "Arrival", "Burst"]
    keys = ["pid", "arrival", "burst"]
    widths = [6, 9, 7]
    if show_priority:
        cols.append("Priority")
        keys.append("priority")
        widths.append(10)
    cols += ["Start", "Completion", "Waiting", "Turnaround"]
    keys += ["start", "completion", "waiting", "turnaround"]
    widths += [7, 12, 9, 10]

    print("".join(c.ljust(w) for c, w in zip(cols, widths)).rstrip())
    for r in results:
        print("".join(str(r[k]).ljust(w) for k, w in zip(keys, widths)).rstrip())


def print_one(key, workload, quantum):
    if key == "mlfq":
        log = []
        results = run_algorithm(key, workload, quantum, log)
        print(f"{'Time':<7}{'PID':<6}{'Queue':<8}Action")
        for t, pid, queue, action in log:
            print(f"{t:<7}{pid:<6}{queue:<8}{action}")
        avg_wait = averages(results)[0]
        print(f"\nAverage Waiting Time: {avg_wait:.2f}")
    else:
        results = run_algorithm(key, workload, quantum)
        print_table(results, show_priority=(key == "priority"))
        avg_wait, avg_turn, _ = averages(results)
        print(f"\nAverage Waiting Time:    {avg_wait:.2f}")
        print(f"Average Turnaround Time: {avg_turn:.2f}")


def print_compare(workload, quantum):
    print(f"{'Algorithm':<15}{'Avg Waiting':<13}{'Avg Turnaround':<16}Avg Response")
    for key, (name, _) in ALGORITHMS.items():
        w, t, r = averages(run_algorithm(key, workload, quantum))
        print(f"{name:<15}{w:<13.2f}{t:<16.2f}{r:.2f}")


def main():
    parser = argparse.ArgumentParser(description="CPU scheduler simulator")
    parser.add_argument("--workload", required=True, help="csv file: pid,arrival,burst,priority")
    parser.add_argument("--algo", choices=list(ALGORITHMS), help="fcfs, sjf, rr, priority, or mlfq")
    parser.add_argument("--compare", action="store_true", help="compare all five algorithms")
    parser.add_argument("--quantum", type=int, default=DEFAULT_QUANTUM, help="round robin quantum (default 4)")
    args = parser.parse_args()

    if not args.algo and not args.compare:
        parser.error("give --algo <name> or --compare")
    if args.quantum <= 0:
        parser.error("--quantum must be positive")

    workload = load_workload(args.workload)
    if args.compare:
        print_compare(workload, args.quantum)
    else:
        print_one(args.algo, workload, args.quantum)


if __name__ == "__main__":
    main()
