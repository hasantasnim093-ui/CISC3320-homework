#!/usr/bin/env python3
# CISC 3320 - HW2: Job-Control Shell
import os
import sys
import shlex
import signal


class Job:
    def __init__(self, pid, command, background):
        self.pid = pid
        self.command = command
        self.background = background
        self.status = "Running"  # Running, Done


jobs = {}         # job_id -> Job
next_job_id = 1


def reap_children():
    # Collect finished children without blocking (WNOHANG), so no zombies.
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:   # no children at all
            break
        if pid == 0:                # children exist but none are finished
            break
        for job in jobs.values():
            if job.pid == pid:
                job.status = "Done"


def run_external(args, command, background):
    global next_job_id
    sys.stdout.flush()
    pid = os.fork()
    if pid == 0:
        # child: replace ourselves with the program
        try:
            os.execvp(args[0], args)
        except OSError:
            print(f"myshell: {args[0]}: command not found", flush=True)
        os._exit(127)   # exec only returns on error

    # parent
    if background:
        jobs[next_job_id] = Job(pid, command, True)
        print(f"[{next_job_id}] {pid} {command}")
        next_job_id += 1
    else:
        os.waitpid(pid, 0)   # foreground: wait for it to finish


def do_cd(args):
    path = args[0] if args else os.environ.get("HOME", "/")
    try:
        os.chdir(path)       # must run in the shell itself, not a child
    except OSError as e:
        print(f"myshell: cd: {path}: {e.strerror}")


def do_jobs():
    reap_children()
    for job_id in sorted(jobs):
        print(f"[{job_id}]  {jobs[job_id].status:<10} {jobs[job_id].command}")
    for job_id in [i for i in jobs if jobs[i].status == "Done"]:
        del jobs[job_id]     # reported once, now forget it


def get_job(args, name):
    if len(args) != 1 or not args[0].isdigit() or int(args[0]) not in jobs:
        print(f"myshell: {name}: no such job")
        return None
    return int(args[0])


def do_fg(args):
    job_id = get_job(args, "fg")
    if job_id is None:
        return
    job = jobs[job_id]
    print(job.command)
    if job.status == "Running":
        os.waitpid(job.pid, 0)   # block until it finishes
    del jobs[job_id]


def do_kill(args):
    job_id = get_job(args, "kill")
    if job_id is None:
        return
    job = jobs[job_id]
    if job.status == "Running":
        os.kill(job.pid, signal.SIGTERM)
        os.waitpid(job.pid, 0)   # reap it right away, no zombie
        print(f"[{job_id}]  Terminated  {job.command}")
    del jobs[job_id]


def do_exit():
    for job in jobs.values():
        if job.status == "Running":
            os.kill(job.pid, signal.SIGTERM)
            os.waitpid(job.pid, 0)
    sys.exit(0)


def main():
    while True:
        reap_children()                      # reap before every prompt
        try:
            line = input("myshell> ").strip()   # read
        except EOFError:
            print()
            do_exit()
        if not line:
            continue

        background = False                   # parse
        if line.endswith("&"):
            background = True
            line = line[:-1].strip()
        try:
            args = shlex.split(line)
        except ValueError:
            print("myshell: parse error")
            continue
        if not args:
            continue

        cmd = args[0]                        # execute
        if cmd == "cd":
            do_cd(args[1:])
        elif cmd == "jobs":
            do_jobs()
        elif cmd == "fg":
            do_fg(args[1:])
        elif cmd == "kill":
            do_kill(args[1:])
        elif cmd == "exit":
            do_exit()
        else:
            run_external(args, line, background)


if __name__ == "__main__":
    main()
