#!/bin/python

# Boxplots of the evaluation (Sect. 4.2): one plot per approach and scenario, the categories on the x-axis and the
# costs of the alignments of their process instances on the y-axis (whiskers at 1.5 IQR, outliers as points).
# Per category, one box for the instances without (blue, left), one for the instances with the additional iteration
# (vermillion, middle; EXTRA.json, cf. data_sets/make_classes.rb), and one for all instances of the category (green,
# right). The plots are sized for a width of about half the
# LNCS text width (fonts about 6-7 pt in print).
# The file names follow those of the figures in the paper (figures/evaluation/{syntheticB_short,syntheticB}/...),
# written directly into OUT_DIR.
#
# e.g., python plot.py RESULTS_DIR OUT_DIR EXTRA.json

import sys
import os
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

PLOTS = {
  'syntheticB_short': {
    'cff_short': 'results_control_flow_first_syntheticB_short_xml',
    'balanced_short': 'results_balanced_syntheticB_short_xml',
    'cfo_short': 'results_control_flow_only_syntheticB_short_xml',
    'sacf_short': 'results_sensor_data_as_control_flow_syntheticB_short_xml',
  },
  'syntheticB': {
    'cff_full': 'results_control_flow_first_syntheticB_xml',
    'balanced_full': 'results_balanced_syntheticB_xml',
    'cfo_full': 'results_control_flow_only_syntheticB_xml',
    'cfo_desired_full': 'results_control_flow_only_syntheticB_desired_xml',
    'sacf_full': 'results_sensor_data_as_control_flow_syntheticB_xml',
    'sacf_desired_full': 'results_sensor_data_as_control_flow_syntheticB_desired_xml',
  },
}
CATEGORIES = ['a','b','c']
GROUPS = [('without iteration', False, '#0072B2'),  # additional iteration; None = all instances
          ('with iteration', True, '#D55E00'),
          ('all', None, '#009E73')]
OFFSET = 0.27  # distance of the outer boxes of a category from its center
FONT = 9       # pt in the 3.2 in wide plot, i.e., about 6.5 pt at half the LNCS text width

def plot(results_path, out_base, extra):
  results = json.load(open(results_path))
  found = {n: r for n,r in results.items() if r['alignment_found']}
  missing = [sum(1 for r in results.values() if r['category'] == c and not r['alignment_found']) for c in CATEGORIES]
  plt.rcParams.update({'font.size': FONT})
  fig, ax = plt.subplots(figsize=(3.2, 2.4))
  handles = []
  for g,(group,with_extra,color) in enumerate(GROUPS):
    costs = [[r['cost'] for n,r in found.items()
              if r['category'] == c and (with_extra is None or (n in extra) == with_extra)] for c in CATEGORIES]
    positions = [i + 1 + (g - 1) * OFFSET for i in range(len(CATEGORIES))]
    line = {'color': color, 'linewidth': 0.9}
    ax.boxplot(costs, positions=positions, whis=1.5, widths=0.22,
               medianprops={'color': color, 'linewidth': 1.8}, boxprops=line, whiskerprops=line, capprops=line,
               flierprops={'marker': 'o', 'markersize': 2.5, 'markerfacecolor': color, 'markeredgecolor': color})
    handles.append(Line2D([], [], color=color, linewidth=1.8, label=group))
  counts = lambda c, with_extra: sum(1 for n,r in found.items() if r['category'] == c and (n in extra) == with_extra)
  ax.set_xticks(range(1, len(CATEGORIES) + 1))
  ax.set_xticklabels([f"{c.upper()}\n(n={counts(c, False)}+{counts(c, True)}" + (f", {m} n/a)" if m else ")")
                      for c,m in zip(CATEGORIES, missing)])
  ax.set_xlim(0.45, len(CATEGORIES) + 0.55)
  ax.set_xlabel('Category')
  ax.set_ylabel('Cost')
  top = max(r['cost'] for r in found.values())
  ax.set_ylim(-0.04 * top if top > 0 else -0.04, 1.08 * top if top > 0 else 1)
  ax.grid(axis='y', color='0.85', linewidth=0.5)
  ax.set_axisbelow(True)
  ax.legend(handles=handles, loc='lower left', bbox_to_anchor=(0, 1.01), ncol=3, frameon=False, handlelength=1.5,
            columnspacing=0.8, borderaxespad=0, fontsize=FONT - 1)
  fig.tight_layout(pad=0.2)
  for ext in ['svg','pdf']:
    fig.savefig(f"{out_base}.{ext}", bbox_inches='tight', pad_inches=0.02)
  plt.close(fig)

def main():
  results_dir, out_dir, extra_path = sys.argv[1:4]
  extra = {i for ids in json.load(open(extra_path)).values() for i in ids}
  os.makedirs(out_dir, exist_ok=True)
  for scenario,plots in PLOTS.items():
    for result,name in plots.items():
      path = os.path.join(results_dir, f"{result}.json")
      if not os.path.exists(path):
        print(f"missing {path}")
        continue
      plot(path, os.path.join(out_dir, name), extra)
      print(f"{result}.json -> {name}.{{svg,pdf}}")

if __name__ == '__main__':
  main()
