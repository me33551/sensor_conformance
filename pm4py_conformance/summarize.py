#!/bin/python

# Summarizes result files of conformance.py (or merge_folds.py): per category the number of traces, min,
# quartiles, median, mean and max of the costs, and the separability of the desired executions (category "b"):
# - AUC = probability that a non-desired instance has a higher cost than a desired one (ties count 1/2), for
#   b vs. a+c, b vs. a, and b vs. c, with a 95% bootstrap confidence interval (resampled per category).
# - Threshold detection: per fold, the threshold is the maximum cost of the training "b" instances under that
#   fold's model, i.e., an instance is detected if it costs more than every desired execution used for fitting;
#   reported are the shares of held-out "b" (false alarms) and of "a" and "c" with a cost above it. Results without fold costs (nothing fitted, e.g., Control Flow Only) use their cost
#   for every fold.
#
# e.g., python summarize.py folds/folds.json cff_short.json balanced_short.json ...

import sys
import json
import random
import statistics

CATEGORIES = ['a','b','c']
BOOTSTRAP = 2000

def quantile(values, q):
  values = sorted(values)
  pos = q * (len(values) - 1)
  lo = int(pos)
  hi = min(lo + 1, len(values) - 1)
  return values[lo] + (values[hi] - values[lo]) * (pos - lo)

def auc(positive, negative):
  # Mann-Whitney U / (|positive| |negative|) with midranks for ties; costs rounded to absorb float noise
  values = sorted([(round(v, 6), 1) for v in positive] + [(round(v, 6), 0) for v in negative])
  rank_sum = 0.0
  i = 0
  while i < len(values):
    j = i
    while j < len(values) and values[j][0] == values[i][0]:
      j += 1
    midrank = (i + 1 + j) / 2
    rank_sum += midrank * sum(1 for x in values[i:j] if x[1] == 1)
    i = j
  u = rank_sum - len(positive) * (len(positive) + 1) / 2
  return u / (len(positive) * len(negative))

def aucs(costs):
  return [auc(costs['a'] + costs['c'], costs['b']), auc(costs['a'], costs['b']), auc(costs['c'], costs['b'])]

def bootstrap(costs):
  rng = random.Random(0)
  samples = []
  for _ in range(BOOTSTRAP):
    samples.append(aucs({c: [rng.choice(v) for _ in v] for c,v in costs.items()}))
  return [(quantile([s[i] for s in samples], .025), quantile([s[i] for s in samples], .975)) for i in range(3)]

def detection(results, folds, selected=None):
  # the threshold of fold f is learned from the fitting instances (the ids in the folds) not held out in f;
  # all other instances (held-out fitting instances, all instances not used for fitting) are counted;
  # selected: optional set of instances to count (e.g., only those with an extra iteration)
  # every instance counts once: a held-out fitting instance with its fold, all others with the share of folds
  # in which they are flagged
  held_out_in = {i: f for f,ids in enumerate(folds) for i in ids}
  flagged = {c: 0.0 for c in CATEGORIES}
  total = {c: 0 for c in CATEGORIES}
  thresholds = []
  for f in range(len(folds)):
    training = [r['fold_costs'][f] if 'fold_costs' in r else r['cost'] for n,r in results.items() if n in held_out_in and held_out_in[n] != f]
    thresholds.append(max(training))
  for n,r in results.items():
    if selected is not None and n not in selected:
      continue
    fold_cost = lambda f: r['fold_costs'][f] if 'fold_costs' in r else r['cost']
    counted = [held_out_in[n]] if n in held_out_in else range(len(folds))
    total[r['category']] += 1
    flagged[r['category']] += sum(fold_cost(f) > thresholds[f] + 1e-6 for f in counted) / len(counted)
  return {c: flagged[c] / total[c] if total[c] else float('nan') for c in CATEGORIES}

def main():
  folds = json.load(open(sys.argv[1]))
  for path in sys.argv[2:]:
    summarize(path, folds)

def summarize(path, folds):
  results = json.load(open(path))
  costs = {c: [r['cost'] for r in results.values() if r['category'] == c and r['alignment_found']] for c in CATEGORIES}
  missing = {c: sum(1 for r in results.values() if r['category'] == c and not r['alignment_found']) for c in CATEGORIES}
  print(f"== {path}")
  print(f"  {'cat':3} {'n':>3} {'n/a':>3} {'min':>9} {'q1':>9} {'median':>9} {'mean':>9} {'q3':>9} {'max':>9}")
  for c in CATEGORIES:
    v = costs[c]
    if not v:
      print(f"  {c.upper():3} {0:3} {missing[c]:3}")
      continue
    print(f"  {c.upper():3} {len(v):3} {missing[c]:3} {min(v):9.2f} {quantile(v,.25):9.2f} {statistics.median(v):9.2f} {statistics.mean(v):9.2f} {quantile(v,.75):9.2f} {max(v):9.2f}")
  if any(missing.values()):
    print(f"  no alignment found: " + ', '.join(f"{c.upper()} {missing[c]}" for c in CATEGORIES))
  point = aucs(costs)
  interval = bootstrap(costs)
  print(f"  AUC " + '   '.join(f"{name} {p:.3f} [{lo:.3f}, {hi:.3f}]" for name,p,(lo,hi) in zip(['B/AC','B/A','B/C'], point, interval)))
  rates = detection({n: r for n,r in results.items() if r['alignment_found']}, folds)
  print(f"  flagged (cost > maximum of training B): " + '   '.join(f"{c.upper()} {100.0 * rates[c]:.1f}%" for c in CATEGORIES))

if __name__ == '__main__':
  main()
