# CISC 3320 - HW3 Report: Scheduler Simulator

Tasnim Hasan

## How to run

```
python3 simulator.py --workload sample.csv --algo fcfs     # fcfs | sjf | rr | priority | mlfq
python3 simulator.py --workload sample.csv --compare
python3 simulator.py --workload my_workload.csv --compare
```
`--quantum N` changes the Round Robin quantum (default 4). Workload files are CSV: `pid,arrival,burst,priority`.

## Design decisions

**General**
- Every algorithm has the same shape, `schedule(processes, quantum=None)`, and returns `(pid, start, end)` segments.
- One shared `compute_metrics()` computes everything from those segments:
  waiting = turnaround - burst, turnaround = completion - arrival, response = first start - arrival.
- Each algorithm runs on a `deepcopy` of the workload, so `remaining_time` always starts fresh.
- If the CPU is idle (nothing has arrived yet), time jumps to the next arrival.

**Round Robin** - quantum 4. New arrivals join the queue *before* the preempted process is re-queued. A process that finishes exactly at the quantum boundary is not re-queued.

**Priority**
- Lower number = higher priority.
- Non-preemptive: the choice is only made when the CPU frees up.
- Aging: effective priority = priority - (time waited // 5), so waiting processes slowly move up and cannot starve.
- Tie-break: earlier arrival first, then whoever is listed first in the file.

**MLFQ**
- 3 queues: Q0 (quantum 4), Q1 (quantum 8), Q2 (quantum 16). Everyone starts in Q0.
- Demotion: a process that uses its full quantum and is not finished drops one queue (Q2 stays in Q2).
- Within a queue: FIFO. Always run the front of the highest non-empty queue.
- Boost: every 50 time units everyone is moved back to Q0 (checked between slices).
- A slice always runs to the end of its quantum (a new arrival does not interrupt it).
- "Stays put on I/O": my workload format has no I/O, so no process ever blocks early. A process that finishes before its quantum is simply done, so it is never demoted. The rule is only implied.

## Validation (Lecture 5 workload, `sample.csv`)

| Algorithm   | Avg Waiting | Avg Turnaround | Avg Response |
|-------------|-------------|----------------|--------------|
| FCFS        | 7.50        | 12.25          | 7.50         |
| SJF         | 4.50        | 9.25           | 4.50         |
| Round Robin | 8.50        | 13.25          | 5.00         |
| Priority    | 9.00        | 13.75          | 9.00         |
| MLFQ        | 8.50        | 13.25          | 5.00         |

FCFS (7.5) and SJF (4.5) match Lecture 5's hand-computed answers exactly. All five rows match the lecture's expected output.

## My own workload (`my_workload.csv`)

6 processes, staggered arrivals, an idle gap (CPU is empty from t=28 to t=30), and one long job (P6, burst 20).

| Algorithm   | Avg Waiting | Avg Turnaround | Avg Response |
|-------------|-------------|----------------|--------------|
| FCFS        | 7.17        | 15.67          | 7.17         |
| SJF         | 6.50        | 15.00          | 6.50         |
| Round Robin | 9.33        | 17.83          | 3.33         |
| Priority    | 6.50        | 15.00          | 6.50         |
| MLFQ        | 8.83        | 17.33          | 3.33         |

I also checked by hand that FCFS gives 43/6 = 7.17 average wait here.

**Observations**
- SJF has the lowest average wait, as expected. Priority ties it by coincidence: P1 runs first either way, and the priorities happen to order the other jobs the same as their burst lengths.
- Round Robin and MLFQ have the best response time (3.33) because every process gets the CPU quickly, but the worst waiting and turnaround, because long jobs get chopped up and finish later.
- This workload finishes before t=50, so the MLFQ priority boost never triggers here.
