#!/bin/julia

using Distances
using DynamicAxisWarping
using JSON

# Distance between two time series (FastDTW, squared Euclidean) for many pairs in one julia process.
#
# e.g., ./get_dtw_batch.jl pairs.json   with pairs.json = [[[1.0,2.0,...],[1.5,2.5,...]], ...]
# prints [cost1, cost2, ...]; null for pairs with an empty or non-numeric time series

pairs = JSON.parsefile(ARGS[1])
costs = map(pairs) do pair
  x = pair[1]
  y = pair[2]
  if isempty(x) || isempty(y) || !all(el -> isa(el,Number),x) || !all(el -> isa(el,Number),y)
    nothing
  else
    cost,i1,i2 = fastdtw(Float64.(x),Float64.(y),SqEuclidean(),500)
    cost
  end
end
println(JSON.json(costs))
