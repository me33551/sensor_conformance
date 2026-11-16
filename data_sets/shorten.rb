#!/bin/ruby

require 'yaml'
require 'fileutils'

# Crops the logs of all instances of a process directly after the "activity/done" event of task F,
# i.e., the "activity/done" event of F is kept and all following events are removed. Both the sorted
# YAML logs (used for calculating the desired sensor data) and the sorted XML logs (used by PM4Py)
# are cropped. The text of the kept events is copied unchanged. index.txt is copied as well.
#
# e.g., ./shorten.rb syntheticB syntheticB_short single_optionA

CROP_TASK = 'F'
CROP_LIFECYCLE = 'activity/done'

# A "stream/data" event is written as a result of the directly preceding "activity/receiving" event of its
# activity and contains the sensor data received there. If the crop falls between the two (the stream/data
# event is logged a few ms later), the stream/data event is kept as well, so that no receiving is left
# without its sensor data.
# events: list of [activity, lifecycle]; returns the indices of the events after crop_at that are kept
def completing_events(events,crop_at)
  last_lifecycle = {}
  events[0..crop_at].each() { |activity,lifecycle| last_lifecycle[activity] = lifecycle unless lifecycle == 'dataelements/change' }
  kept = []
  pending = last_lifecycle.select() { |_,lifecycle| lifecycle == 'activity/receiving' }.keys()
  events.each_with_index() { |(activity,lifecycle),i|
    next if i <= crop_at || !pending.include?(activity) || lifecycle == 'dataelements/change'
    kept.push(i) if lifecycle == 'stream/data'
    pending.delete(activity)
  }
  kept
end

def crop_yaml(from,to)
  docs = File.read(from).split(/^(?=---\s*$)/)
  parsed = docs.map() { |doc| e = YAML.unsafe_load(doc); e.is_a?(Hash) && e['event'] ? [e.dig('event','cpee:activity'), e.dig('event','cpee:lifecycle:transition'), e.dig('event','concept:name')] : [nil,nil,nil] }
  crop_at = parsed.index() { |activity,lifecycle,name| name == CROP_TASK && lifecycle == CROP_LIFECYCLE }
  if(crop_at.nil?()) then
    File.write(to,docs.join())
    return [false, docs.length() - 1, docs.length() - 1, 0]
  end
  completing = completing_events(parsed.map() { |p| p[0,2] },crop_at)
  File.write(to,(docs[0..crop_at] + completing.map() { |i| docs[i] }).join())
  [true, crop_at + completing.length(), docs.length() - 1, completing.length()]
end

def crop_xml(from,to)
  xml = File.read(from)
  events = xml.to_enum(:scan,/<event[ >].*?<\/event>/m).map() { Regexp.last_match() }
  parsed = events.map() { |m| [m[0][/key="cpee:activity" value="([^"]*)"/,1], m[0][/key="cpee:lifecycle:transition" value="([^"]*)"/,1], m[0][/key="concept:name" value="([^"]*)"/,1]] }
  crop_at = parsed.index() { |activity,lifecycle,name| name == CROP_TASK && lifecycle == CROP_LIFECYCLE }
  if(crop_at.nil?()) then
    File.write(to,xml)
    return [false, events.length(), events.length(), 0]
  end
  completing = completing_events(parsed.map() { |p| p[0,2] },crop_at)
  separator = xml[events[0].end(0)...events[1].begin(0)]
  tail = xml[xml.rindex(/^\s*<\/trace>/)..-1]
  File.write(to,xml[0...events[crop_at].end(0)] + completing.map() { |i| separator + events[i][0] }.join() + "\n" + tail)
  [true, crop_at + 1 + completing.length(), events.length(), completing.length()]
end

FileUtils.mkdir_p(ARGV[1])
FileUtils.cp(File.join(ARGV[0],'index.txt'),File.join(ARGV[1],'index.txt'))

File.read(File.join(ARGV[0],'index.txt')).split("\n").each() { |line|
  match = line.match(/.+#{ARGV[2]} \((.+)\) - \d+/)
  next if match.nil?()
  instance_uuid = match[1]
  yaml_result = crop_yaml(File.join(ARGV[0],"#{instance_uuid}.sorted.xes.yaml"),File.join(ARGV[1],"#{instance_uuid}.sorted.xes.yaml"))
  xml_result = crop_xml(File.join(ARGV[0],"#{instance_uuid}.sorted.xes.xml"),File.join(ARGV[1],"#{instance_uuid}.sorted.xes.xml"))
  puts "#{instance_uuid} yaml: found=#{yaml_result[0]} kept #{yaml_result[1]}/#{yaml_result[2]} events (#{yaml_result[3]} completing), xml: found=#{xml_result[0]} kept #{xml_result[1]}/#{xml_result[2]} events (#{xml_result[3]} completing)"
}
