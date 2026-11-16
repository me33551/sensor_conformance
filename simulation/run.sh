#!/bin/bash
# Simulates the synthetic dataset on cpee.org and downloads its logs.
#
# 1. checks that the simulation service (server.rb, lehre.bpm.in.tum.de/ports/4570) answers and that the
#    process model in the CPEE hub is the same as models/single_optionA.xml (the parent instance starts the
#    hub version, not the local file)
# 2. creates an instance of models/execute_multiple_optionA.xml via the engine API and starts it; it forks
#    NUMBER instances of single_optionA (one per second)
# 3. waits until the parent and all forked instances are finished
# 4. downloads the logs of the parent and of all forked instances into data_sets/DATASET (index.txt lists
#    them), sorts them by time:timestamp and converts them to XES XML (cpee-logging-xes-yaml)
# 5. prints the final states, the decisions (a, b, c) and the number of instances with extra iteration
#
# The cropped dataset and the class files are created by eval.sh (data_sets/shorten.rb, make_classes.rb).
#
# e.g., ./run.sh syntheticC          (150 instances)
#       ./run.sh -n 10 test10        (10 instances)

set -euo pipefail

SIM="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMPL="$(dirname "$SIM")"
ENGINE=https://cpee.org/flow/engine
LOGS=https://cpee.org/logs
HUB=https://cpee.org/hub/server/Staff.dir/Ehrendorfer.dir/conformance.dir/synthetic_adapted.dir
SERVICE=https://lehre.bpm.in.tum.de/ports/4570
TOOL="${XES_TOOL:-$HOME/Projects/cpee-logging-xes-yaml/tools/cpee-logging-xes-yaml}"
POLL=10

NUMBER=150
while getopts "n:" opt; do
  case $opt in
    n) NUMBER=$OPTARG ;;
    *) echo "usage: $0 [-n NUMBER] DATASET" >&2; exit 1 ;;
  esac
done
shift $((OPTIND - 1))
if [ $# -ne 1 ]; then echo "usage: $0 [-n NUMBER] DATASET" >&2; exit 1; fi
OUT="$IMPL/data_sets/$1"
if [ -e "$OUT" ]; then echo "$OUT already exists" >&2; exit 1; fi
[ -x "$TOOL" ] || { echo "cpee-logging-xes-yaml not found: $TOOL (set XES_TOOL)" >&2; exit 1; }

log() { echo "[$(date +%H:%M:%S)] $*"; }
state() { curl -s -m 20 "$ENGINE/$1/properties/state/"; }

# 1. checks
code=$(curl -s -m 20 -o /dev/null -w '%{http_code}' "$SERVICE/?riddl-description")
[ "$code" = 200 ] || { echo "simulation service $SERVICE does not answer (HTTP $code)" >&2; exit 1; }
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -s -m 20 -f -o "$TMP/hub.xml" "$HUB/single_optionA.xml" || { echo "process model not found in the hub" >&2; exit 1; }
if ! diff -q -w "$TMP/hub.xml" "$SIM/models/single_optionA.xml" > /dev/null; then
  echo "the hub version of single_optionA.xml differs from models/single_optionA.xml:" >&2
  diff -w "$TMP/hub.xml" "$SIM/models/single_optionA.xml" | head -20 >&2
  read -r -p "continue with the hub version? [y/N] " a
  [ "$a" = y ] || exit 1
fi

# 2. parent instance with NUMBER instances
sed "s|<number_of_instances>[0-9]*</number_of_instances>|<number_of_instances>$NUMBER</number_of_instances>|" \
  "$SIM/models/execute_multiple_optionA.xml" > "$TMP/execute_multiple.xml"
id=$(curl -s -m 20 -X POST "$ENGINE/" -F "testset=@$TMP/execute_multiple.xml;type=application/xml")
[[ "$id" =~ ^[0-9]+$ ]] || { echo "creating the instance failed: $id" >&2; exit 1; }
uuid=$(curl -s -m 20 "$ENGINE/$id/properties/attributes/uuid/")
curl -s -m 20 -f -X PUT "$ENGINE/$id/properties/state/" --data-urlencode 'value=running' -o /dev/null
echo "$id $uuid" > "$SIM/run_parent.txt"
log "parent instance $id ($uuid) started, $NUMBER instances; monitor: https://cpee.org/flow/?monitor=$ENGINE/$id/"

# 3. wait for the parent, then for every forked instance
while true; do
  s=$(state "$id")
  case "$s" in
    finished) break ;;
    running|ready) sleep $POLL ;;
    *) echo "parent instance $id is $s" >&2; exit 1 ;;
  esac
done
log "parent finished"
(cd "$TMP" && "$TOOL" view "$LOGS/$uuid.xes.yaml" > /dev/null)
mapfile -t children < <(grep -E '^ +single_optionA \(' "$TMP/index.txt" | sed -E 's/.* - ([0-9]+)$/\1/')
[ ${#children[@]} -eq "$NUMBER" ] || { echo "found ${#children[@]} instead of $NUMBER forked instances" >&2; exit 1; }
for c in "${children[@]}"; do
  while true; do
    s=$(state "$c")
    case "$s" in
      finished) break ;;
      running|ready|stopping) sleep $POLL ;;
      *) echo "instance $c is $s" >&2; exit 1 ;;
    esac
  done
done
log "all ${#children[@]} instances finished"

# 4. download, sort, convert
mkdir -p "$OUT"
cd "$OUT"
"$TOOL" copy "$LOGS/$uuid.xes.yaml" > /dev/null
"$TOOL" sort > /dev/null
"$TOOL" to-xes-xml > /dev/null
n=$(ls *.sorted.xes.xml | wc -l)
[ "$n" -eq $((NUMBER + 1)) ] || { echo "expected $((NUMBER + 1)) logs, found $n" >&2; exit 1; }
log "logs in $OUT"

# 5. summary
python3 -I - "$OUT" <<'EOF'
import sys, os, re, collections, yaml
d = sys.argv[1]
uuids = [re.search(r'single_optionA \((.+)\)', l).group(1) for l in open(os.path.join(d, 'index.txt')) if 'single_optionA (' in l]
states, cats = collections.Counter(), collections.Counter()
for u in uuids:
    evs = [x['event'] for x in yaml.safe_load_all(open(os.path.join(d, u + '.sorted.xes.yaml'))) if x and 'event' in x]
    st = [e['cpee:state'] for e in evs if e.get('cpee:lifecycle:transition') == 'state/change' and 'cpee:state' in e]
    states[st[-1] if st else None] += 1
    values = {v['name']: v['value'] for e in evs if e.get('cpee:lifecycle:transition') == 'dataelements/change' for v in e.get('data', [])}
    cats[(values.get('decision'), str(values.get('extra')))] += 1
print('final states:', dict(states))
for (dec, extra), n in sorted(cats.items(), key=str):
    print(f'decision {dec}, extra iteration {extra}: {n}')
EOF
