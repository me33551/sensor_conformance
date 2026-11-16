#!/bin/julia

using Distances
using DynamicAxisWarping
using JSON

# DTW Barycenter Average (DBA) of the time series in the given files ({"data": {"data": [{"value": ...}, ...]}});
# prints the average as a JSON array ([] if all time series are empty). Missing values count as 0.
# The DBA is initialized with the medoid (the time series with the minimal sum of FastDTW distances to all
# others), so the result is deterministic.
#
# e.g., ./get_dba.jl [path1] [path2] ...

timeseries = []

for path in ARGS
  dict = JSON.parsefile(path)
  try
    push!(timeseries,map((el) -> isnothing(el["value"]) ? 0.0 : Float64(el["value"]), dict["data"]["data"]))
  catch e
  end
end

if(all((el) -> isempty(el),timeseries))
  println(JSON.json([]))
else
  timeseries = filter((el) -> !isempty(el),timeseries)
  sums = map((x) -> sum(map((y) -> fastdtw(x,y,SqEuclidean(),500)[1],timeseries)),timeseries)
  medoid = timeseries[argmin(sums)]
  avg, res = dba(timeseries,FastDTW(100); init_center=medoid, show_progress=false)
  println(JSON.json(avg))
end
