#!/bin/python

# Sensor Data as Control Flow (SaCF): the sensor data of a "stream/data" event is turned into one symbol per
# sensor, which is then used as control flow (event label "[aid]_[sensor]_[symbol]").
#
# One symbol per sensor and "stream/data" event (i.e., per occurrence k):
#   peak      the maximum lies inside the time series and is more than eps above its first and its last point
#   increase  otherwise, if the least squares trend over the time series (slope * (n-1)) is larger than eps
#   decrease  otherwise, if the trend is smaller than -eps
#   stable    otherwise (also for time series with less than 2 points)
# eps is the noise of the sensor in the desired executions: the median absolute difference between two
# consecutive points in their "stream/data" events (cf. calculate_desired_symbols.py).

import statistics

SYMBOLS = ['decrease', 'increase', 'peak', 'stable']

def trend(values):
  n = len(values)
  mean_x = (n - 1) / 2
  mean_y = sum(values) / n
  sxx = sum((i - mean_x) ** 2 for i in range(n))
  sxy = sum((i - mean_x) * (v - mean_y) for i,v in enumerate(values))
  return (sxy / sxx) * (n - 1)

def symbol(values, eps):
  if len(values) < 2:
    return 'stable'
  top = max(range(len(values)), key=lambda i: values[i])
  if 0 < top < len(values) - 1 and values[top] - values[0] > eps and values[top] - values[-1] > eps:
    return 'peak'
  change = trend(values)
  if change > eps:
    return 'increase'
  if change < -eps:
    return 'decrease'
  return 'stable'

def step_noise(series_list):
  steps = [abs(b - a) for values in series_list for a,b in zip(values, values[1:])]
  return statistics.median(steps) if steps else 0.0

def label(aid, sen, sym):
  return f"{aid}_{sen}_{sym}"
