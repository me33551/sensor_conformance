#!/bin/python

# Iteration deviations: compares the instances with a repeated
# measurement at the beginning of "record" (extra iteration, cf. data_sets/make_classes.rb) with the other
# instances of the same category.
# - AUC (b vs. a+c, b vs. a, b vs. c, 95% bootstrap interval) among the instances without and among the instances
#   with extra iteration: if the extra iteration only adds the cost of the iteration deviation (two log moves) to
#   every instance, the separation of the categories is the same in both groups.
# - Per category the difference of the mean costs (extra - without extra), split into control flow costs and
#   sensor-based costs (for Control Flow First including 2 c_L + d_min for occurrences without desired sensor
#   data; for Balanced including d_min of log moves of "stream/data" events). The cost of the iteration
#   deviation itself is 100 (two log moves) plus d_min of the repeated "stream/data" event, so ideally
#   d cf = 100 and d sensor is small.
# - Share of instances above the per-fold threshold (cf. summarize.py), separately for both groups.
#
# e.g., python extra_summary.py FOLDS.json EXTRA.json cff_short.json balanced_short.json ...

import sys
import json
import statistics

from summarize import CATEGORIES, aucs, bootstrap, detection

def main():
  folds = json.load(open(sys.argv[1]))
  extra = {i for ids in json.load(open(sys.argv[2])).values() for i in ids}
  for path in sys.argv[3:]:
    results = {n: r for n,r in json.load(open(path)).items() if r['alignment_found']}
    print(f"== {path}")
    for name, group in [('without extra', lambda n: n not in extra), ('with extra', lambda n: n in extra)]:
      costs = {c: [r['cost'] for n,r in results.items() if r['category'] == c and group(n)] for c in CATEGORIES}
      point = aucs(costs)
      interval = bootstrap(costs)
      rates = detection(results, folds, {n for n in results if group(n)})
      print(f"  {name:14} n " + '/'.join(str(len(costs[c])) for c in CATEGORIES) + "  AUC " +
        '   '.join(f"{label} {p:.3f} [{lo:.3f}, {hi:.3f}]" for label,p,(lo,hi) in zip(['B/AC','B/A','B/C'], point, interval)) +
        "  flagged " + ' '.join(f"{c.upper()} {100.0 * rates[c]:.1f}%" for c in CATEGORIES))
    for c in CATEGORIES:
      with_extra = [r for n,r in results.items() if r['category'] == c and n in extra]
      without = [r for n,r in results.items() if r['category'] == c and n not in extra]
      d = lambda key: statistics.mean(r[key] for r in with_extra) - statistics.mean(r[key] for r in without)
      print(f"  {c.upper()}: mean cost {statistics.mean(r['cost'] for r in without):8.2f} -> {statistics.mean(r['cost'] for r in with_extra):8.2f}"
            f"   d cost {d('cost'):8.2f}   d cf {d('control_flow_cost'):8.2f}   d sensor {d('sensor_cost'):8.2f}")

if __name__ == '__main__':
  main()
