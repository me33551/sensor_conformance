#!/usr/bin/ruby
#
# Sensor data simulation for the synthetic dataset.
#
# - GET record starts the simulation of the calling instance and answers without body (CPEE-CALLBACK: true),
#   so CPEE waits for the callbacks and logs no "activity/receiving" without data.
# - One callback per phase: each update contains the whole time series of a phase (one window), so every
#   "stream/data" event is one occurrence of the data transition.
# - Regular, simulated timestamps (start + i * interval, ISO 8601 with milliseconds); the thread sleeps until
#   the next tick, so the HTTP latency does not stretch the time series.
# - The course is a schedule of phases given by the process model (behavior, level/target, noise, points);
#   GET decide draws the decision and replaces the phases from position "at" on with the phases of the option.
# - Streams are identified by the instance (CPEE-INSTANCE-UUID header).
# - All random numbers come from a seed given by the process model, so a dataset can be regenerated.
#
# Phase (JSON): {"name": "ramp", "behavior": "ramp", "to": 12, "noise": 0.3, "points": 10}
#   steady: level + noise (level defaults to the value at the start of the phase)
#   ramp:   linear from the value at the start of the phase to "to" over the phase, + noise
#   noise:  standard deviation of normally distributed noise (default 0)
#   min/max: optional clamping of every value
#
# e.g., ruby server.rb      (listens on ::1 port 4570, behind the nginx of lehre at /ports/4570/)

require 'json'
require 'time'
require 'riddl/server'
require 'typhoeus'

PORT = (ENV['SIM_PORT'] || 4570).to_i
BIND = ENV['SIM_BIND'] || '::1'

def param(p, name)
  x = p.find { |e| e.name == name }
  x.nil? ? nil : x.value
end

def gaussian(rng)
  # Box-Muller
  Math.sqrt(-2.0 * Math.log(1.0 - rng.rand())) * Math.cos(2.0 * Math::PI * rng.rand())
end

def value_of(phase, start_value, j, rng)
  n = phase['points'].to_i
  base = case phase['behavior']
    when 'steady' then phase['level'].nil? ? start_value : phase['level'].to_f
    when 'ramp'   then start_value + (phase['to'].to_f - start_value) * (j + 1).to_f / n
    else raise "unknown behavior #{phase['behavior']}"
  end
  v = base + phase['noise'].to_f * gaussian(rng)
  v = [v, phase['min'].to_f].max unless phase['min'].nil?
  v = [v, phase['max'].to_f].min unless phase['max'].nil?
  v
end

class Streams
  # instance uuid => { schedule: [phases], phase: index of the running phase, ... }
  def initialize
    @streams = {}
    @mutex = Mutex.new
  end
  def synchronize(&block) = @mutex.synchronize(&block)
  def [](k) = @streams[k]
  def []=(k, v)
    @streams[k] = v
  end
  def delete(k) = @streams.delete(k)
end

def simulate(streams, instance, callback, stream_name, interval, start_value, rng)
  t0 = Time.now
  i = 0
  value = start_value
  phase_index = 0
  loop do
    phase = nil
    last = false
    streams.synchronize do
      s = streams[instance]
      phase = s[:schedule][phase_index]
      s[:phase] = phase_index
      last = phase_index == s[:schedule].length - 1
    end
    start = value
    points = []
    phase['points'].to_i.times do |j|
      t = t0 + (i + 1) * interval
      wait = t - Time.now
      sleep(wait) if wait > 0
      value = value_of(phase, start, j, rng)
      points << { 'value' => value, 'timestamp' => t.iso8601(3) }
      i += 1
    end
    # the schedule may have been extended or changed by "decide" while the phase was running
    streams.synchronize { last = phase_index == streams[instance][:schedule].length - 1 }
    headers = { 'Content-Type' => 'application/json' }
    headers['CPEE-UPDATE'] = 'true' unless last
    response = Typhoeus.put(callback, headers: headers,
      body: { 'stream' => stream_name, 'phase' => phase['name'], 'points' => points }.to_json)
    break if last || !response.success?
    phase_index += 1
  end
ensure
  streams.synchronize { streams.delete(instance) }
end

class Record < Riddl::Implementation
  def response
    streams = @a[0]
    instance = @h['CPEE_INSTANCE_UUID']
    callback = @h['CPEE_CALLBACK']
    schedule = JSON.parse(param(@p, 'phases'))
    interval = param(@p, 'interval').to_f
    seed = param(@p, 'seed').to_i
    start_value = (param(@p, 'start') || 5).to_f
    stream_name = param(@p, 'stream')
    if instance.nil? || callback.nil? || schedule.empty?
      @status = 400
      return
    end
    streams.synchronize { streams[instance] = { schedule: schedule, phase: 0 } }
    Thread.new { simulate(streams, instance, callback, stream_name, interval, start_value, Random.new(seed)) }
    # no body: CPEE waits for the callbacks and logs no "activity/receiving" for this answer
    @headers << Riddl::Header.new('CPEE-CALLBACK', 'true')
    nil
  end
end

class Decide < Riddl::Implementation
  def response
    streams = @a[0]
    instance = @h['CPEE_INSTANCE_UUID']
    options = JSON.parse(param(@p, 'options'))
    outcomes = JSON.parse(param(@p, 'outcomes'))
    at = param(@p, 'at').to_i
    rng = Random.new(param(@p, 'seed').to_i)

    number = rng.rand() * options.values.sum(0.0)
    decision = options.keys.find { |o| (number -= options[o]) < 0 } || options.keys.last
    ok = streams.synchronize do
      s = streams[instance]
      # only phases that have not started yet can be replaced
      if s && s[:phase] < at
        s[:schedule] = s[:schedule][0...at] + outcomes[decision]
        true
      else
        false
      end
    end
    unless ok
      @status = 409
      return Riddl::Parameter::Complex.new('return', 'application/json',
        { 'error' => "no stream of instance #{instance} before phase #{at}" }.to_json)
    end
    Riddl::Parameter::Complex.new('return', 'application/json', { 'decision' => decision }.to_json)
  end
end

Riddl::Server.new(File.join(__dir__, 'server.xml'), :bind => BIND, :port => PORT) do
  accessible_description true
  cross_site_xhr false

  streams = Streams.new

  on resource do
    on resource 'record' do
      run Record, streams if get 'record_params'
    end
    on resource 'decide' do
      run Decide, streams if get 'decide_params'
    end
  end
end.loop!
