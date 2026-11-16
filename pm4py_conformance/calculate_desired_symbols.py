#!/bin/python

# Desired symbols for Sensor Data as Control Flow (SaCF), the counterpart of the desired sensor data Des (step 2):
# from the desired executions (category "b"), eps per activity and sensor (noise, cf. symbols.py) and, per
# activity, occurrence k and sensor, the most frequent symbol of their k-th "stream/data" event (ties are
# broken alphabetically).
#
# e.g., python calculate_desired_symbols.py LOG_DIR CLASSES.json OUT.json [PROCESS_NAME]
# writes {"eps": {aid: {sen: eps}}, "desired": {aid: [{sen: symbol}, ...]}, "counts": {aid: [{sen: {symbol: n}}]}}

import sys
import os
import re
import json
from collections import Counter

from conformance import load_trace
from symbols import symbol, step_noise, SYMBOLS

def main():
  log_dir, classes_path, out_path = sys.argv[1:4]
  process_name = sys.argv[4] if len(sys.argv) > 4 else 'single_optionA'
  desired_instances = set(json.load(open(classes_path))['b'])

  names = []
  with open(os.path.join(log_dir,'index.txt')) as f:
    for line in f:
      m = re.match(rf".+{process_name} \((.+)\) - \d+", line)
      if m and m.group(1) in desired_instances:
        names.append(m.group(1))

  # series[aid][k][sen] = list of time series of the desired executions
  series = {}
  for n in names:
    for e in load_trace(os.path.join(log_dir, f"{n}.sorted.xes.xml"), True):
      if e['lifecycle'] != 'stream/data':
        continue
      occurrences = series.setdefault(e['aid'], {})
      for sen,values in e['data'].items():
        occurrences.setdefault(e['k'], {}).setdefault(sen, []).append(values)

  eps = {}
  desired = {}
  counts = {}
  for aid,occurrences in series.items():
    sensors = sorted({sen for per_k in occurrences.values() for sen in per_k})
    eps[aid] = {sen: step_noise([v for per_k in occurrences.values() for v in per_k.get(sen, [])]) for sen in sensors}
    desired[aid] = []
    counts[aid] = []
    for k in range(1, max(occurrences) + 1):
      per_sen = {}
      count_per_sen = {}
      for sen,values_list in sorted(occurrences.get(k, {}).items()):
        c = Counter(symbol(v, eps[aid][sen]) for v in values_list)
        per_sen[sen] = sorted(c.items(), key=lambda x: (-x[1], x[0]))[0][0]
        count_per_sen[sen] = {s: c.get(s, 0) for s in SYMBOLS}
      desired[aid].append(per_sen)
      counts[aid].append(count_per_sen)

  with open(out_path,'w') as f:
    json.dump({'eps': eps, 'desired': desired, 'counts': counts}, f, indent=1)
  print(json.dumps({'eps': eps, 'desired': desired, 'counts': counts}))

if __name__ == '__main__':
  main()
