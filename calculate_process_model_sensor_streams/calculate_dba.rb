#!/bin/ruby

require 'yaml'
require 'hpath'
require 'json'

# e.g., ./calculate_dba.rb synthetic_logs_xml/optionA/ single_optionA

file_content = File.read(File.join(ARGV[0],'index.txt'))
classes = JSON.parse(File.read(File.join(__dir__,'classes',"classes_#{ARGV[0].split('/').last()}.json")))

sensor_data_per_instance_per_activity_per_event = {}
lines = file_content.split("\n")
lines.each() { |line|
  match = line.match(/.+#{ARGV[1]} \((.+)\) - \d+/)
  if(match.nil?().!()) then
    pp match[1]
    instance_uuid = match[1]
    io = File.open(File.join(ARGV[0],"#{instance_uuid}.sorted.xes.yaml"))
    sensor_data_per_instance_per_activity_per_event[instance_uuid] ||= {}
    YAML.load_stream(io) do |e|
      if(e.dig('event','cpee:lifecycle:transition') == 'stream/data') then
        activity_id = e.dig('event','cpee:activity')
        event_uuid = e.dig('event','cpee:activity_uuid')
        stream_data = e.dig('event','stream:datastream')
        stream_points = Hpath.get(stream_data,'//stream:point')
        stream_points = stream_points.group_by() { |sp|
          sp['stream:id']
        }
        #stream_points = stream_points.map() { |k,v|
        #  [k, [v]]
        #}.to_h()
        sensor_data_per_instance_per_activity_per_event[instance_uuid][activity_id] ||= {}
        sensor_data_per_instance_per_activity_per_event[instance_uuid][activity_id][event_uuid] ||= []
        sensor_data_per_instance_per_activity_per_event[instance_uuid][activity_id][event_uuid].push(stream_points)
        #sensor_data_per_instance_per_activity_per_event[instance_uuid][activity_id][event_uuid].nil?() ? sensor_data_per_instance_per_activity_per_event[instance_uuid][activity_id][event_uuid] = stream_points : sensor_data_per_instance_per_activity_per_event[instance_uuid][activity_id][event_uuid].merge(stream_points) { |key,old_value,new_value| old_value.concat(new_value)}
      end
    end
  end
}
#pp sensor_data_per_instance_per_activity_per_event

File.open(File.join('sensor_streams',"#{ARGV[0].gsub('/',' ').strip().gsub(' ','_')}_raw.json"), 'w') do |file|
  file.write(sensor_data_per_instance_per_activity_per_event.to_json())
end

files_per_activity_per_stream_per_index = {}
sensor_data_per_instance_per_activity_per_event.each() { |instance_id,sensor_data_per_activity_per_event|
  sensor_data_per_activity_per_event.each() { |activity_id,sensor_data_per_event|
    sensor_data_per_event.each() { |event_id,sensor_data_per_streamevent|
      pp "#{instance_id}/#{activity_id}/#{event_id}"
      sensor_data_per_streamevent.each_with_index() { |sensor_data_per_individualstreamevent,index|
        sensor_data_per_individualstreamevent.each() { |stream_id,points|
          write_to_file = points.map() { |point| {:value => point['stream:value'], :timestamp => point['stream:timestamp']} }
          file_path = File.join(__dir__,'dtw','datastream_files',"#{instance_id}_#{activity_id}_#{event_id}_#{stream_id}_#{index}.json")
          # only the desired executions define occurrences: an occurrence k that no desired execution has (e.g.,
          # the 4th window of an instance with an extra iteration) has no Des
          if(classes['b'].include?(instance_id)) then
            files_per_activity_per_stream_per_index[activity_id] ||= {}
            files_per_activity_per_stream_per_index[activity_id][stream_id] ||= []
            files_per_activity_per_stream_per_index[activity_id][stream_id][index] ||= []
            files_per_activity_per_stream_per_index[activity_id][stream_id][index].push(file_path)
          end
          File.open(file_path, 'w') do |file|
            file.write({:data => {:data => write_to_file} }.to_json())
          end
        }
      }
    }
  }
}

dbas_per_activity_per_index_per_stream = {}
files_per_activity_per_stream_per_index.each() { |activity_id,files_per_activity|
  files_per_activity.each() { |stream_id,files_per_index|
    files_per_index.each_with_index() { |files,index|
      result = `julia dtw/get_dba.jl #{files.join(' ')}`
      dbas_per_activity_per_index_per_stream[activity_id] ||= []
      dbas_per_activity_per_index_per_stream[activity_id][index] ||= {}
      dbas_per_activity_per_index_per_stream[activity_id][index][stream_id] ||= JSON.parse(result).map().with_index() { |el,index| {:value => el, :timestamp => Time.at(index)} }
    }
  }
}
pp dbas_per_activity_per_index_per_stream

File.open(File.join('sensor_streams',"#{ARGV[0].gsub('/',' ').strip().gsub(' ','_')}.json"), 'w') do |file|
  file.write(dbas_per_activity_per_index_per_stream.to_json())
end

# Normal deviation delta(t,k,sen) (step 2 of the paper): the mean distance between the sensor data of sen in
# the k-th "stream/data" event of t of the desired executions and Des(t,k,sen). If it is 0, the normal
# deviation of sen pooled over all occurrences of t is used, and if that is 0 as well, 1 (cf. Discussion).
values = lambda { |points| points.map() { |point| point['stream:value'] } }
pairs = []
pair_keys = []
sensor_data_per_instance_per_activity_per_event.each() { |instance_id,sensor_data_per_activity_per_event|
  next unless classes['b'].include?(instance_id)
  sensor_data_per_activity_per_event.each() { |activity_id,sensor_data_per_event|
    sensor_data_per_event.each() { |event_id,sensor_data_per_streamevent|
      sensor_data_per_streamevent.each_with_index() { |sensor_data_per_individualstreamevent,index|
        sensor_data_per_individualstreamevent.each() { |stream_id,points|
          desired = dbas_per_activity_per_index_per_stream.dig(activity_id,index,stream_id)
          next if desired.nil?()
          pairs.push([values.call(points), desired.map() { |el| el[:value] }])
          pair_keys.push([activity_id,index,stream_id])
        }
      }
    }
  }
}
File.write(File.join(__dir__,'dtw','pairs.json'),pairs.to_json())
distances = JSON.parse(`julia dtw/get_dtw_batch.jl #{File.join(__dir__,'dtw','pairs.json')}`)

distances_per_key = {}
pair_keys.each_with_index() { |key,i|
  next if distances[i].nil?()
  (distances_per_key[key] ||= []).push(distances[i])
}
mean = lambda { |list| list.empty?() ? 0.0 : list.sum() / list.length() }
deltas_per_activity_per_index_per_stream = {}
dbas_per_activity_per_index_per_stream.each() { |activity_id,dbas_per_index|
  deltas_per_activity_per_index_per_stream[activity_id] = []
  dbas_per_index.each_with_index() { |dbas_per_stream,index|
    deltas_per_activity_per_index_per_stream[activity_id][index] = {}
    (dbas_per_stream || {}).each_key() { |stream_id|
      delta = mean.call(distances_per_key[[activity_id,index,stream_id]] || [])
      if(delta == 0.0) then
        pooled = distances_per_key.select() { |key,_| key[0] == activity_id && key[2] == stream_id }.values().flatten()
        delta = mean.call(pooled)
        delta = 1.0 if delta == 0.0
      end
      deltas_per_activity_per_index_per_stream[activity_id][index][stream_id] = delta
    }
  }
}
pp deltas_per_activity_per_index_per_stream

File.open(File.join('sensor_streams',"#{ARGV[0].gsub('/',' ').strip().gsub(' ','_')}_delta.json"), 'w') do |file|
  file.write(deltas_per_activity_per_index_per_stream.to_json())
end
