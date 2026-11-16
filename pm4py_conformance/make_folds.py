#!/bin/python

# Cross-validation folds over the desired executions (category "b"): Des, delta, eps and the desired symbols are
# fitted on the training part of "b" only, and every "b" instance is scored with the model of the fold in which
# it is held out. "a" and "c" are never used for fitting and are scored with every fold model.
# The "b" ids are sorted and assigned to fold index mod N (deterministic).
#
# e.g., python make_folds.py CLASSES.json N OUT_DIR
# writes OUT_DIR/folds.json ([[held-out b ids of fold 1], ...]) and OUT_DIR/classes_f<f>.json (b = training part)

import sys
import os
import json

def main():
  classes_path, n, out_dir = sys.argv[1], int(sys.argv[2]), sys.argv[3]
  classes = json.load(open(classes_path))
  desired = sorted(classes['b'])
  folds = [[i for j,i in enumerate(desired) if j % n == f] for f in range(n)]
  os.makedirs(out_dir, exist_ok=True)
  with open(os.path.join(out_dir, 'folds.json'), 'w') as f:
    json.dump(folds, f, indent=1)
  for f,held_out in enumerate(folds, start=1):
    training = dict(classes)
    training['b'] = [i for i in desired if i not in held_out]
    with open(os.path.join(out_dir, f"classes_f{f}.json"), 'w') as out:
      json.dump(training, out)
    print(f"fold {f}: {len(held_out)} held out, {len(training['b'])} training")

if __name__ == '__main__':
  main()
