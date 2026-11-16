# Evaluation on sensor_conformance

Synthetic dataset and evaluation for sensor-based conformance.

## Simulation (`simulation/`)

The simulation (i.e., creation of the dataset) can be run with:

```bash
 ./run.sh
```

- `server.rb`, `description.xml`: riddl service (port 4570, `ruby server.rb -v start`, runs on
  lehre.bpm.in.tum.de/ports/4570). `GET record` starts the sensor simulation of an instance and answers
  asynchronously with one callback per phase (one window of 10 points, 1 s apart, regular timestamps);
  `GET decide` draws the decision (weights a:b:c = 2:3:1) and replaces the remaining phases with those of the
  option. All random numbers come from the seed given by the instance. See the header of `server.rb`.
- `models/single_optionA.xml`: the process (CPEE hub: Staff.dir/Ehrendorfer.dir/conformance.dir/synthetic_adapted.dir).
  "init simulation" draws the seed and, in 30% of the instances, a repeated warmup phase at the beginning of
  "record" (extra iteration; the decision then replaces phase 3 instead of 2). Phases: warmup (steady 5),
  increase (to 12), outcome: a steady, b (desired) decrease to 3, c increase to 18. The alternatives of the decision have
  the eids e4 (a), e2 (b, desired; used by `--keep e2`) and e3 (c).
- `models/single_optionA_short.xml`: the same without the decision (for the cropped scenario).
- `models/execute_multiple_optionA.xml`: starts 150 instances.
- `run.sh DATASET` (`-n NUMBER`, default 150): checks the service and the hub model, starts
  `execute_multiple_optionA.xml` via the engine API, waits until all instances are finished, and downloads,
  sorts and converts the logs into `data_sets/DATASET`.
- `run_parent.txt`: CPEE instance and uuid of the parent run that produced the dataset (written by `run.sh`).

## Data (`data_sets/syntheticB`)

Logs of the 150 instances (cpee.org/logs/<uuid>.xes.yaml, sorted with sort``, converted with `to-xes-xml` of
cpee-logging-xes-yaml), `index.txt`. Categories a 51 (16 with extra iteration), b 74 (19), c 25 (6); every
"stream/data" event of "record" holds one window of 10 points.

## Pipeline

The evaluation can be run with:

```bash
 ./eval.sh
```

`./eval.sh` does the following (all steps, 5-fold cross-validation):

1. `data_sets/shorten.rb`: crops the logs after "activity/done" of F which creates `syntheticB_short`;
   `data_sets/make_classes.rb`: creates `classes_syntheticB.json` (category = logged
   decision), `_fit.json` (b without extra iteration is later, used for fitting), `_extra.json` (instances with extra
   iteration).
2. `pm4py_conformance/make_folds.py`: 5 folds over the b instances of `_fit.json` -> results are in `folds/`.
3. per fold: Des and delta (`calculate_process_model_sensor_streams/calculate_dba.rb`, Julia DBA/FastDTW in
   `dtw/`), desired symbols (`calculate_desired_symbols.py`), petri nets (`cpee_tree_to_pn/cpee_to_pn_class`),
   conformance checking (`conformance.py`) for Control Flow First, Balanced, Sensor Data as Control Flow
   (for the short, full, and desired scenario).
4. `merge_folds.py`: held-out b instances get the cost of their fold, all others (a, c, b with extra
   iteration) the mean over the folds. Control Flow Only fits nothing and runs once.
5. `summarize.py` -> `results/summary.txt` (quartiles, AUC with bootstrap interval, threshold detection);
   `extra_summary.py` -> `results/summary_extra.txt` (instances with vs. without extra iteration: AUC, cost
   difference split into control flow and sensor costs, detection); `fitness_summary.py` ->
   `results/summary_fitness.txt` (fitness 1 - cost / worst-case cost per category and AUC on the fitness, for
   all instances and with/without extra iteration); `plot.py` → boxplots in `results/`.
6. Temporary files (DTW input files, `pairs.json`) are removed.

`venv` contains the dependencies of PM4Py; the used PM4Py itself is in `pm4py_src`.

The results used for the evaluation can be found in `results`.

# Generative AI Usage:
Generative AI was used for code restructuring and code debugging.
