#!/bin/bash
# CISC 3320 - HW4: time both versions on the SAME workload
# usage: bash run_compare.sh
echo "cores: $(nproc)"
for work in io cpu; do
  for prog in pc_threading.py pc_multiprocessing.py; do
    python3 $prog --producers 3 --consumers 3 --capacity 5 --items 20 --work $work --quiet | grep elapsed
  done
done
