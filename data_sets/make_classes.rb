#!/bin/ruby
require 'yaml'
require 'json'

# Class files for the simulated dataset (simulation/server.rb): the category of an instance is its logged
# "decision" (a, b, c), and "extra" marks instances with a repeated measurement at the beginning of "record".
# Writes
#   OUT_PREFIX.json        {"a": [...], "b": [...], "c": [...]}             categories of all instances
#   OUT_PREFIX_fit.json    the same, but "b" without extra iteration      desired executions used for fitting
#   OUT_PREFIX_extra.json  {"a": [...], "b": [...], "c": [...]}             instances with extra iteration
#
# e.g., ./make_classes.rb syntheticB single_optionA ../calculate_process_model_sensor_streams/classes/classes_syntheticB

log_dir, process_name, out_prefix = ARGV[0,3]
classes = { 'a' => [], 'b' => [], 'c' => [] }
extra = { 'a' => [], 'b' => [], 'c' => [] }

File.read(File.join(log_dir,'index.txt')).split("\n").each() { |line|
  match = line.match(/.+#{process_name} \((.+)\) - \d+/)
  next if match.nil?()
  instance = match[1]
  values = {}
  File.read(File.join(log_dir,"#{instance}.sorted.xes.yaml")).split(/^(?=---\s*$)/).each() { |doc|
    e = YAML.unsafe_load(doc)
    e = e.is_a?(Hash) ? e['event'] : nil
    next unless e.is_a?(Hash) && e['cpee:lifecycle:transition'] == 'dataelements/change'
    (e['data'] || []).each() { |d| values[d['name']] = d['value'] }
  }
  decision = values['decision']
  classes[decision].push(instance)
  extra[decision].push(instance) if values['extra'] == true
}

fit = classes.merge('b' => classes['b'] - extra['b'])
[['',classes],['_fit',fit],['_extra',extra]].each() { |suffix,content|
  File.write("#{out_prefix}#{suffix}.json",JSON.pretty_generate(content.transform_values() { |v| v.sort() }))
}
puts "#{out_prefix}: " + classes.map() { |c,v| "#{c} #{v.length()} (#{extra[c].length()} extra)" }.join(', ')
