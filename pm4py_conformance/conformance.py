#!/bin/python

# Conformance checking as defined in the paper (Sects. "Preparation", "Control Flow First", "Balanced").
#
#   approach cff:      Control Flow First - control flow alignment on the net with data transitions (loop),
#                      then c(gamma) + sum d(t,k,w) over the synchronous moves of data transitions,
#                      d replaced by 2 c_L + d_min(w) if Des(t,k,.) is undefined, plus d_min(w) for every log
#                      move of a "stream/data" event
#   approach balanced: Balanced - net with unrolled receiving/data pairs t^1..t^K, the cost of a synchronous
#                      move of a "stream/data" event e and t^k is d(t,k,w_e), the cost of its log move
#                      c_L + d_min(w_e); result c(gamma)
#   approach cfo:      Control Flow Only - "stream/data" events are ignored, net without data transitions
#   approach sacf:     Sensor Data as Control Flow - every "stream/data" event is replaced by one event per sensor
#                      labeled "[aid]_[sensor]_[symbol]" (cf. symbols.py), net with unrolled pairs whose data
#                      transitions carry the desired symbols (cpee_to_pn_class --symbols); result c(gamma)
#                      (DESIRED.json is the output of calculate_desired_symbols.py, DELTA.json is not used)
#
# Costs: c_L for a log move, c_M for a model move on a visible transition, 0 for a model move on an invisible
# transition, 0 for a synchronous move unless stated otherwise (Def. Alignment).
# d(t,k,w) = sum over sen in dom(w) of dist(w(sen), Des(t,k,sen)) / delta(t,k,sen), dist = FastDTW.
# d_min(w) = min over k of d(t,k,w), i.e., the deviation of w from the closest desired occurrence of t, so that
# a "stream/data" event that is not compared with the desired sensor data of its own occurrence (log move, or an
# occurrence beyond the desired ones) still costs according to how much its sensor data deviates.
#
# k of a "stream/data" event is its position among the "stream/data" events of the same activity in the trace,
# i.e., the same counting as for Des(t,k,sen) in the desired executions (step 2).
#
# Fitness: 1 - cost / W, with the worst-case cost W = sum of the log move costs of all events (c_L, for
# "stream/data" events of cff and balanced c_L + d_min(w)) + the cost of the cheapest run of the net from the
# initial to the final marking (model moves only). For balanced, W is the cost of an alignment of the same net,
# so the fitness lies in [0, 1]; for cff, the sensor costs are not bounded by W, so the fitness is clipped at 0.
#
# e.g., python conformance.py cff LOG_DIR NET.pnml DESIRED.json DELTA.json CLASSES.json OUT.json [PROCESS_NAME]

import sys
import os
import re
import json
import subprocess
from lxml import etree

from pm4py.objects.petri_net.importer import importer as pn_importer
from pm4py.objects.petri_net.obj import PetriNet, Marking
from pm4py.objects.petri_net.utils import petri_utils
from pm4py.objects.petri_net.utils.synchronous_product import construct_cost_aware
from pm4py.objects.petri_net.utils import align_utils as utils
from pm4py.algo.conformance.alignments.petri_net.variants import state_equation_a_star

from symbols import symbol, label as symbol_label

C_L = 50
C_M = 50
SCALE = 1000  # costs are passed to the A* as integers (in 1/SCALE), results are reported in the paper's units

KEPT_LIFECYCLES = ['activity/calling','activity/receiving','stream/data','activity/done']
XES = '{http://www.xes-standard.org/}'

def event_attributes(event):
  attributes = {}
  for child in event:
    key = child.get('key')
    if key is not None and child.get('value') is not None:
      attributes[key] = child.get('value')
  return attributes

def stream_points(event):
  points = {}
  for child in event:
    if child.get('key') == 'stream:datastream':
      for point in child.iter():
        if point.get('key') == 'stream:point':
          values = {c.get('key'): c.get('value') for c in point}
          points.setdefault(values['stream:id'],[]).append(float(values['stream:value']))
  return points

def load_trace(path, with_data):
  """ step (purple) 1 and 2: filter events and label them "[aid]_[lifecycle after '/']" """
  root = etree.parse(path).getroot()
  trace = []
  for event in root.iter(f"{XES}event"):
    attributes = event_attributes(event)
    lifecycle = attributes.get('cpee:lifecycle:transition')
    if lifecycle not in KEPT_LIFECYCLES:
      continue
    if lifecycle == 'stream/data' and not with_data:
      continue
    # script tasks are not part of the Petri Net; their only kept event is "activity/done", which (unlike the
    # events of service calls) has no endpoint
    if lifecycle == 'activity/done' and 'concept:endpoint' not in attributes:
      continue
    aid = attributes['cpee:activity']
    trace.append({
      'label': f"{aid}_{lifecycle.split('/')[1]}",
      'aid': aid,
      'lifecycle': lifecycle,
      'data': stream_points(event) if lifecycle == 'stream/data' else {}
    })
  # occurrence k of every "stream/data" event among the "stream/data" events of its activity
  occurrences = {}
  for e in trace:
    if e['lifecycle'] == 'stream/data':
      occurrences[e['aid']] = occurrences.get(e['aid'],0) + 1
      e['k'] = occurrences[e['aid']]
  return trace

def to_symbols(trace, eps):
  """ SaCF: replace every "stream/data" event by one event per sensor (sorted by sensor) labeled with its symbol """
  result = []
  for e in trace:
    if e['lifecycle'] != 'stream/data':
      result.append(e)
      continue
    for sen in sorted(e['data'].keys()):
      sym = symbol(e['data'][sen], eps[e['aid']][sen])
      result.append({'label': symbol_label(e['aid'], sen, sym), 'aid': e['aid'], 'lifecycle': 'stream/analysis',
                     'data': {}, 'k': e['k'], 'sensor': sen, 'symbol': sym})
  return result

def desired(des, aid, k, sen=None):
  occ = des.get(aid,[])
  if k < 1 or k > len(occ) or not occ[k-1]:
    return None
  if sen is None:
    return occ[k-1]
  return occ[k-1].get(sen)

def compute_distances(traces, des, approach):
  """ all distances dist(w(sen), Des(t,k,sen)) needed, computed with one julia call """
  pairs = []
  keys = []
  for name,trace in traces.items():
    for i,e in enumerate(trace):
      if e['lifecycle'] != 'stream/data':
        continue
      for k in range(1, len(des.get(e['aid'],[])) + 1):
        for sen,values in e['data'].items():
          d = desired(des, e['aid'], k, sen)
          if d is None:
            continue
          pairs.append([[p['value'] for p in d], values])
          keys.append((name,i,k,sen))
  path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'dtw','pairs.json')
  with open(path,'w') as f:
    json.dump(pairs,f)
  result = subprocess.run(['julia', os.path.join(os.path.dirname(os.path.abspath(__file__)),'dtw','get_dtw_batch.jl'), path], capture_output=True, text=True, check=True)
  return dict(zip(keys, json.loads(result.stdout)))

def sensor_deviation(name, i, e, k, des, delta, distances):
  """ d(t,k,w), None if Des(t,k,.) is undefined """
  if desired(des, e['aid'], k) is None:
    return None
  d = 0.0
  for sen in e['data'].keys():
    if desired(des, e['aid'], k, sen) is None:
      continue
    dist = distances.get((name,i,k,sen))
    if dist is None:
      continue
    d += dist / delta[e['aid']][k-1][sen]
  return d

def min_deviation(name, i, e, des, delta, distances):
  """ d_min(w) = min over k of d(t,k,w), 0 if no desired sensor data exists for the activity """
  ds = [sensor_deviation(name, i, e, k, des, delta, distances) for k in range(1, len(des.get(e['aid'],[])) + 1)]
  ds = [d for d in ds if d is not None]
  return min(ds) if ds else 0.0

def align(trace, net, im, fm, sync_cost, log_cost=lambda i: C_L):
  """ optimal alignment with log_cost(i) for the log move of event i, c_M, 0 for invisible transitions,
      sync_cost(i, t_model) for synchronous moves """
  trace_net = PetriNet('trace')
  places = [PetriNet.Place(f"p_{i}") for i in range(len(trace) + 1)]
  for p in places:
    trace_net.places.add(p)
  trace_costs = {}
  for i,e in enumerate(trace):
    t = PetriNet.Transition(f"t_{i}", e['label'])
    trace_net.transitions.add(t)
    petri_utils.add_arc_from_to(places[i], t, trace_net)
    petri_utils.add_arc_from_to(t, places[i+1], trace_net)
    trace_costs[t] = int(round(log_cost(i) * SCALE))
  trace_im = Marking({places[0]: 1})
  trace_fm = Marking({places[-1]: 1})
  model_costs = {t: (C_M * SCALE if t.label is not None else 0) for t in net.transitions}
  sync_costs = {}
  for t_trace in trace_net.transitions:
    for t_model in net.transitions:
      if t_trace.label == t_model.label:
        sync_costs[(t_trace, t_model)] = int(round(sync_cost(int(t_trace.name.split('_')[1]), t_model) * SCALE))
  sync_prod, sync_im, sync_fm, cost_function = construct_cost_aware(
    trace_net, trace_im, trace_fm, net, im, fm, utils.SKIP, trace_costs, model_costs, sync_costs)
  result = state_equation_a_star.apply_sync_prod(sync_prod, sync_im, sync_fm, cost_function, utils.SKIP, ret_tuple_as_trans_desc=True)
  if result is None:
    return None
  moves = []
  for (t_trace, t_model), (l_trace, l_model) in result['alignment']:
    i = int(t_trace.split('_')[1]) if t_trace != utils.SKIP else None
    moves.append({'log': l_trace, 'model': l_model, 'model_transition': t_model, 'index': i,
                  'cost': cost_function[[t for t in sync_prod.transitions if t.name == (t_trace, t_model)][0]] / SCALE})
  return {'cost': result['cost'] / SCALE, 'moves': moves, 'visited_states': result['visited_states']}

def model_run_cost(net, im, fm):
  """ cost of the cheapest run of the net from im to fm, i.e., of aligning the empty trace (model moves only) """
  alignment = align([], net, im, fm, lambda i, t_model: 0)
  return alignment['cost']

def move_type(m):
  if m['log'] == utils.SKIP:
    return 'model' if m['model'] is not None else 'model_invisible'
  if m['model'] == utils.SKIP:
    return 'log'
  return 'sync'

def summary_counts(moves):
  counts = {'log': 0, 'model': 0, 'model_invisible': 0, 'sync': 0}
  for m in moves:
    counts[move_type(m)] += 1
  return counts

def main():
  approach, log_dir, net_path, des_path, delta_path, classes_path, out_path = sys.argv[1:8]
  process_name = sys.argv[8] if len(sys.argv) > 8 else 'single_optionA'

  net, im, fm = pn_importer.apply(net_path, pn_importer.Variants.PNML)
  des = json.load(open(des_path)) if approach in ['cff','balanced'] else {}
  delta = json.load(open(delta_path)) if approach in ['cff','balanced'] else {}
  desired_symbols = json.load(open(des_path)) if approach == 'sacf' else {}
  classes = json.load(open(classes_path))
  category = {i: c for c,l in classes.items() for i in l}

  names = []
  with open(os.path.join(log_dir,'index.txt')) as f:
    for line in f:
      m = re.match(rf".+{process_name} \((.+)\) - \d+", line)
      if m:
        names.append(m.group(1))
  traces = {n: load_trace(os.path.join(log_dir, f"{n}.sorted.xes.xml"), approach != 'cfo') for n in names}
  if approach == 'sacf':
    traces = {n: to_symbols(trace, desired_symbols['eps']) for n,trace in traces.items()}
  distances = compute_distances(traces, des, approach) if approach in ['cff','balanced'] else {}
  run_cost = model_run_cost(net, im, fm)

  results = {}
  for n,trace in traces.items():
    def worst_log_cost(i, trace=trace, n=n):
      e = trace[i]
      if approach in ['cff','balanced'] and e['lifecycle'] == 'stream/data':
        return C_L + min_deviation(n, i, e, des, delta, distances)
      return C_L
    worst_cost = sum(worst_log_cost(i) for i in range(len(trace))) + run_cost
    if approach == 'balanced':
      def sync_cost(i, t_model, trace=trace, n=n):
        e = trace[i]
        if e['lifecycle'] != 'stream/data':
          return 0
        k = int(t_model.name.split('^')[1]) if '^' in t_model.name else 1
        d = sensor_deviation(n, i, e, k, des, delta, distances)
        # an unrolled t^k always has Des(t,k,.) defined (K = number of occurrences in the desired executions)
        return d if d is not None else 2 * C_L
      def log_cost(i, trace=trace, n=n):
        e = trace[i]
        if e['lifecycle'] != 'stream/data':
          return C_L
        return C_L + min_deviation(n, i, e, des, delta, distances)
    else:
      def sync_cost(i, t_model):
        return 0
      def log_cost(i):
        return C_L
    alignment = align(trace, net, im, fm, sync_cost, log_cost)
    if alignment is None:
      results[n] = {'category': category.get(n), 'alignment_found': False}
      print(f"{n} {category.get(n)}: no alignment found", flush=True)
      continue
    control_flow_cost = alignment['cost']
    sensor_cost = 0.0
    sensor_cost_per_event = []
    if approach == 'cff':
      for m in alignment['moves']:
        if move_type(m) in ['sync','log'] and trace[m['index']]['lifecycle'] == 'stream/data':
          e = trace[m['index']]
          d_min = min_deviation(n, m['index'], e, des, delta, distances)
          if move_type(m) == 'log':
            d = d_min
          else:
            d = sensor_deviation(n, m['index'], e, e['k'], des, delta, distances)
            d = 2 * C_L + d_min if d is None else d
          sensor_cost += d
          sensor_cost_per_event.append({'event': m['index'], 'k': e['k'], 'move': move_type(m), 'cost': d})
      overall = control_flow_cost + sensor_cost
    elif approach == 'balanced':
      for m in alignment['moves']:
        if move_type(m) == 'sync' and trace[m['index']]['lifecycle'] == 'stream/data':
          sensor_cost_per_event.append({'event': m['index'], 'k': int(m['model_transition'].split('^')[1]), 'move': 'sync', 'cost': m['cost']})
        elif move_type(m) == 'log' and trace[m['index']]['lifecycle'] == 'stream/data':
          sensor_cost_per_event.append({'event': m['index'], 'k': None, 'move': 'log', 'cost': m['cost'] - C_L})
      sensor_cost = sum(c['cost'] for c in sensor_cost_per_event)
      control_flow_cost = alignment['cost'] - sensor_cost
      overall = alignment['cost']
    else:
      overall = control_flow_cost
    counts = summary_counts(alignment['moves'])
    fitness = max(0.0, 1.0 - overall / worst_cost)
    results[n] = {
      'category': category.get(n), 'alignment_found': True,
      'cost': overall, 'control_flow_cost': control_flow_cost, 'sensor_cost': sensor_cost,
      'worst_cost': worst_cost, 'fitness': fitness,
      'sensor_cost_per_event': sensor_cost_per_event, 'moves': counts,
      'log_moves': [m['log'] for m in alignment['moves'] if move_type(m) == 'log'],
      'model_moves': [m['model'] for m in alignment['moves'] if move_type(m) == 'model'],
      'alignment': alignment['moves']
    }
    print(f"{n} {category.get(n)}: cost {overall:.3f} (control flow {control_flow_cost:.3f}, sensor {sensor_cost:.3f}) fitness {fitness:.4f} moves {counts}", flush=True)

  with open(out_path,'w') as f:
    json.dump(results, f)

if __name__ == '__main__':
  main()
