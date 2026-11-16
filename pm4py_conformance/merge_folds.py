#!/bin/python

# Merges the per-fold results of conformance.py (cf. make_folds.py) into one result file in the same format:
# a "b" instance gets the result of the fold in which it is held out, an "a" or "c" instance the result of the
# first fold with cost, control_flow_cost, sensor_cost, worst_cost and fitness replaced by their mean over all
# folds. Every instance
# additionally gets "fold_costs" (its cost under every fold model) and "b" instances "fold" (1-based), which
# summarize.py uses for the threshold detection.
#
# e.g., python merge_folds.py folds/folds.json OUT.json folds/cff_short_f1.json folds/cff_short_f2.json ...

import sys
import json
import statistics

def main():
  folds = json.load(open(sys.argv[1]))
  out_path = sys.argv[2]
  per_fold = [json.load(open(p)) for p in sys.argv[3:]]
  if len(per_fold) != len(folds):
    sys.exit(f"{len(folds)} folds, but {len(per_fold)} result files")
  held_out_in = {i: f for f,ids in enumerate(folds) for i in ids}

  merged = {}
  for n,first in per_fold[0].items():
    records = [results[n] for results in per_fold]
    if not all(r['alignment_found'] for r in records):
      merged[n] = {'category': first['category'], 'alignment_found': False}
      continue
    fold_costs = [r['cost'] for r in records]
    if n in held_out_in:
      record = dict(records[held_out_in[n]])
      record['fold'] = held_out_in[n] + 1
    else:
      record = dict(first)
      for key in ['cost', 'control_flow_cost', 'sensor_cost', 'worst_cost', 'fitness']:
        record[key] = statistics.mean(r[key] for r in records)
    record['fold_costs'] = fold_costs
    merged[n] = record

  with open(out_path, 'w') as f:
    json.dump(merged, f)
  print(f"{out_path}: {len(merged)} traces, {sum(1 for r in merged.values() if 'fold' in r)} held-out b")

if __name__ == '__main__':
  main()
