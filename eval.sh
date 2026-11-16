#!/bin/bash
# Evaluation on the dataset syntheticB (simulated with simulation/server.rb and simulation/models/, see README.md):
# 5-fold cross-validation over the desired executions, all approaches, both scenarios.
# - every "stream/data" event already contains one window (10 points, 1 s apart), no batching needed
# - categories from the logged decision; instances with a repeated measurement at the beginning of "record"
#   (extra iteration) are marked (data_sets/make_classes.rb)
# - Des, delta, eps and the desired symbols are fitted on the desired executions without extra iteration only;
#   desired executions with extra iteration are scored like categories a and c (mean over the fold models)
# - additional summary of the instances with extra iteration (extra_summary.py)
# Results: results/ (results, logs, summary.txt, summary_extra.txt, boxplots), per-fold data in folds/.
#
# e.g., ./eval.sh

set -euo pipefail

IMPL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROCESS=single_optionA
CLS="$IMPL/calculate_process_model_sensor_streams/classes"
CLASSES="$CLS/classes_syntheticB.json"
STREAMS="$IMPL/calculate_process_model_sensor_streams/sensor_streams"
NETS="$IMPL/cpee_tree_to_pn/generated"
MODELS="$IMPL/simulation/models"
RESULTS="$IMPL/results"
FOLDS=5
FD="$IMPL/folds"
PY="$IMPL/venv/bin/python"
export PYTHONPATH="$IMPL/pm4py_src"
S=syntheticB_short
F=syntheticB

quiet() { grep -v -e PM4Py -e License -e 'Docs & Examples' -e 'processintelligence' -e '=====' -e 'Business use' -e '^\s*$' || true; }
net() { ruby cpee_to_pn_class "$@" | grep -v 'something else'; }
# run APPROACH DATASET NET DESIRED DELTA OUT (OUT without extension)
run() {
  "$PY" pm4py_conformance/conformance.py $1 data_sets/$2 "$NETS/$3.pnml" "$4" "$5" "$CLASSES" "$6.json" $PROCESS > "$6.log" 2>&1
  echo "$(basename $6): $(grep -c ' cost ' "$6.log") traces, no alignment found: $(grep -c 'no alignment' "$6.log" || true)"
}

mkdir -p "$RESULTS"

echo "== 1. data: crop after F done, categories"
cd "$IMPL/data_sets"
rm -rf $S
ruby shorten.rb $F $S $PROCESS > shorten.log
ruby make_classes.rb $F $PROCESS "$CLS/classes_syntheticB"

echo "== 2. cross-validation folds over the desired executions without extra iteration"
rm -rf "$FD"
"$PY" "$IMPL/pm4py_conformance/make_folds.py" "$CLS/classes_syntheticB_fit.json" $FOLDS "$FD"

for f in $(seq 1 $FOLDS); do
  echo "== 3. fold $f: desired sensor data and normal deviation"
  cd "$IMPL/calculate_process_model_sensor_streams"
  for d in $F $S; do
    ln -sfn ../data_sets/$d ${d}_f$f
    cp "$FD/classes_f$f.json" classes/classes_${d}_f$f.json
    rm -f dtw/datastream_files/*
    ruby calculate_dba.rb ${d}_f$f $PROCESS > "$FD/dba_${d}_f$f.log"
  done

  echo "== 4. fold $f: desired symbols (Sensor Data as Control Flow)"
  cd "$IMPL/pm4py_conformance"
  "$PY" calculate_desired_symbols.py ../data_sets/$S "$FD/classes_f$f.json" "$FD/symbols_short_f$f.json" $PROCESS | quiet > /dev/null
  "$PY" calculate_desired_symbols.py ../data_sets/$F "$FD/classes_f$f.json" "$FD/symbols_full_f$f.json" $PROCESS | quiet > /dev/null

  echo "== 5. fold $f: Petri Nets"
  cd "$IMPL/cpee_tree_to_pn"
  net "$MODELS/single_optionA_short.xml" --desired "$STREAMS/${S}_f$f.json" --name short_cff_f$f
  net "$MODELS/single_optionA_short.xml" --desired "$STREAMS/${S}_f$f.json" --unroll --name short_balanced_f$f
  net "$MODELS/single_optionA_short.xml" --symbols "$FD/symbols_short_f$f.json" --name short_sacf_f$f
  net "$MODELS/single_optionA.xml" --desired "$STREAMS/${F}_f$f.json" --name full_cff_f$f
  net "$MODELS/single_optionA.xml" --desired "$STREAMS/${F}_f$f.json" --unroll --name full_balanced_f$f
  net "$MODELS/single_optionA.xml" --symbols "$FD/symbols_full_f$f.json" --name full_sacf_f$f
  net "$MODELS/single_optionA.xml" --symbols "$FD/symbols_full_f$f.json" --keep e2 --name desired_sacf_f$f

  echo "== 6. fold $f: conformance checking"
  cd "$IMPL"
  run cff      $S short_cff_f$f      "$STREAMS/${S}_f$f.json" "$STREAMS/${S}_f${f}_delta.json" "$FD/cff_short_f$f"
  run balanced $S short_balanced_f$f "$STREAMS/${S}_f$f.json" "$STREAMS/${S}_f${f}_delta.json" "$FD/balanced_short_f$f"
  run sacf     $S short_sacf_f$f     "$FD/symbols_short_f$f.json" - "$FD/sacf_short_f$f"
  run cff      $F full_cff_f$f       "$STREAMS/${F}_f$f.json" "$STREAMS/${F}_f${f}_delta.json" "$FD/cff_full_f$f"
  run balanced $F full_balanced_f$f  "$STREAMS/${F}_f$f.json" "$STREAMS/${F}_f${f}_delta.json" "$FD/balanced_full_f$f"
  run sacf     $F full_sacf_f$f      "$FD/symbols_full_f$f.json" - "$FD/sacf_full_f$f"
  run sacf     $F desired_sacf_f$f   "$FD/symbols_full_f$f.json" - "$FD/sacf_desired_full_f$f"
done

echo "== 7. merge folds"
for r in cff_short balanced_short sacf_short cff_full balanced_full sacf_full sacf_desired_full; do
  "$PY" "$IMPL/pm4py_conformance/merge_folds.py" "$FD/folds.json" "$RESULTS/$r.json" $(for f in $(seq 1 $FOLDS); do echo "$FD/${r}_f$f.json"; done)
done

echo "== 8. Control Flow Only (nothing fitted, no folds)"
cd "$IMPL/cpee_tree_to_pn"
net "$MODELS/single_optionA_short.xml" --name short_cfo
net "$MODELS/single_optionA.xml" --name full_cfo
net "$MODELS/single_optionA.xml" --keep e2 --name desired_cfo
cd "$IMPL"
run cfo $S short_cfo   - - "$RESULTS/cfo_short"
run cfo $F full_cfo    - - "$RESULTS/cfo_full"
run cfo $F desired_cfo - - "$RESULTS/cfo_desired_full"

echo "== 9. summaries"
cd "$RESULTS"
ALL="cff_short.json balanced_short.json sacf_short.json cfo_short.json cff_full.json balanced_full.json sacf_full.json cfo_full.json sacf_desired_full.json cfo_desired_full.json"
"$PY" "$IMPL/pm4py_conformance/summarize.py" "$FD/folds.json" $ALL > summary.txt
"$PY" "$IMPL/pm4py_conformance/extra_summary.py" "$FD/folds.json" "$CLS/classes_syntheticB_extra.json" $ALL > summary_extra.txt
"$PY" "$IMPL/pm4py_conformance/fitness_summary.py" "$CLS/classes_syntheticB_extra.json" $ALL > summary_fitness.txt
echo "$RESULTS/summary.txt, $RESULTS/summary_extra.txt, $RESULTS/summary_fitness.txt"

echo "== 10. boxplots into $RESULTS"
"$PY" "$IMPL/pm4py_conformance/plot.py" "$RESULTS" "$RESULTS" "$CLS/classes_syntheticB_extra.json"

echo "== 11. remove temporary files"
rm -f "$IMPL"/calculate_process_model_sensor_streams/dtw/datastream_files/* \
      "$IMPL"/calculate_process_model_sensor_streams/dtw/pairs.json "$IMPL"/pm4py_conformance/dtw/pairs.json
rm -rf "$IMPL"/pm4py_conformance/__pycache__
