#!/bin/python

# Fitness summary of result files of conformance.py (or merge_folds.py): fitness = 1 - cost / W (cf. the header
# of conformance.py). For all instances, the instances without and the instances with extra iteration
# (cf. data_sets/make_classes.rb):
# - per category the number of instances, min, median and max of the fitness,
# - AUC = probability that a non-desired instance has a lower fitness than a desired one (ties count 1/2), for
#   b vs. a+c, b vs. a, and b vs. c, with a 95% bootstrap confidence interval (resampled per category).
#
# e.g., python fitness_summary.py EXTRA.json cff_short.json balanced_short.json ...

import sys
import json
import statistics

from summarize import CATEGORIES, aucs, bootstrap

def main():
  extra = {i for ids in json.load(open(sys.argv[1])).values() for i in ids}
  for path in sys.argv[2:]:
    results = {n: r for n,r in json.load(open(path)).items() if r['alignment_found']}
    print(f"== {path}")
    for name, group in [('all', lambda n: True), ('without extra', lambda n: n not in extra), ('with extra', lambda n: n in extra)]:
      fitness = {c: [r['fitness'] for n,r in results.items() if r['category'] == c and group(n)] for c in CATEGORIES}
      print(f"  {name}")
      for c in CATEGORIES:
        v = fitness[c]
        print(f"    {c.upper()} {len(v):3}  min {min(v):.4f}  median {statistics.median(v):.4f}  max {max(v):.4f}")
      # lower fitness = more deviating, so the AUC is computed on the negated fitness
      negated = {c: [-f for f in v] for c,v in fitness.items()}
      point = aucs(negated)
      interval = bootstrap(negated)
      print(f"    AUC " + '   '.join(f"{n} {p:.3f} [{lo:.3f}, {hi:.3f}]" for n,p,(lo,hi) in zip(['B/AC','B/A','B/C'], point, interval)))

if __name__ == '__main__':
  main()
