import numpy as np
import sounddevice as sd
import soundfile as sf
from flask import Flask, request, jsonify

from audio_stream import AudioStream
from globals import input_output_streams
from input_output_audio_stream import InputOutputAudioStream

from globals import streams

app = Flask(__name__)


def list_audio_devices():
    devices = sd.query_devices()
    input_devices = []
    output_devices = []

    for index, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            input_devices.append(f"Input Device {index}: `{device['name']}` - Channels: {device['max_input_channels']}")
        if device['max_output_channels'] > 0:
            output_devices.append(
                f"Output Device {index}: `{device['name']}` - Channels: {device['max_output_channels']}")

    # Print categorized lists
    print("Available input devices:")
    for device in input_devices:
        print(device)
    print("\nAvailable output devices:")
    for device in output_devices:
        print(device)


list_audio_devices()


def find_device_index(device_name, is_input=True):
    devices = sd.query_devices()
    for index, device in enumerate(devices):
        if device_name in device['name']:
            if (is_input and device['max_input_channels'] > 0) or (not is_input and device['max_output_channels'] > 0):
                return index
    raise ValueError(f"Device '{device_name}' not found or does not match the specified type.")


@app.route('/start-loop', methods=['POST'])
def start_audio_loop():
    data = request.get_json()
    input_device_name = data.get('input_device')
    output_device_name = data.get('output_device')
    stream_id = f"{input_device_name}-{output_device_name}"

    volume = data.get('volume', 1.0)
    fade_background_music = data.get('fade_background_music', False)

    if fade_background_music:
        wait_handles = [stream.decrease_volume() for stream in streams.values()]
        for handle in wait_handles:
            handle.wait()

    stream = InputOutputAudioStream(input_device_name, output_device_name, fade_background_music, volume)
    stream.start_streams()
    input_output_streams[stream_id] = stream

    return jsonify({'status': 'success', 'message': 'Audio loop started', 'stream_id': stream_id}), 200


@app.route('/end-loop', methods=['POST'])
def stop_audio_loop():
    data = request.get_json()
    input_device_name = data.get('input_device')
    output_device_name = data.get('output_device')
    stream_id = f"{input_device_name}-{output_device_name}"

    if stream_id in input_output_streams:
        input_output_streams[stream_id].stop_streams()
        del input_output_streams[stream_id]
        return jsonify({'status': 'success', 'message': 'Audio loop stopped'}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Stream ID not found'}), 404


@app.route('/play', methods=['POST'])
def start():
    global streams
    data = request.json
    filepath = data.get('filepath')
    volume = float(data.get('volume', 1.0))
    background_volume = float(data.get('background_volume', 1.0))
    loop = data.get('loop', False)

    if filepath in streams:
        return jsonify({"status": "Error", "message": "Playback is already running for this file"}), 409

    wait_handles = [stream.decrease_volume() for stream in streams.values()]
    for handle in wait_handles:
        handle.wait()

    looping_streams = [stream for stream in streams.values() if stream.loop == loop]
    for stream in looping_streams:
        stream.stop()
        stream.close()
        streams.pop(stream.filepath)

    new_stream = AudioStream(filepath, loop, volume, background_volume)
    streams[filepath] = new_stream
    return jsonify({"status": "Playback started for " + filepath}), 200


@app.route('/duration', methods=['POST'])
def duration():
    data = request.json
    filepath = data.get('filepath')

    with sf.SoundFile(filepath) as sound_file:
        frames = sound_file.frames
        sample_rate = sound_file.samplerate
        duration_seconds = frames / sample_rate
        return jsonify({"durationInSeconds": f"{int(duration_seconds)}"}), 200


def audio_callback(outdata, frames, time, status):
    global streams
    outdata.fill(0)

    for filepath, stream in list(streams.items()):
        if stream.is_playing:
            data = stream.read(frames)
            padding_length = frames - data.shape[0]
            if padding_length > 0:
                data = np.pad(data, ((0, padding_length), (0, 0)), mode='constant', constant_values=0)
            outdata[:] += data
            if not stream.is_playing:
                streams.pop(filepath)


@app.route('/stop', methods=['POST'])
def stop():
    global streams
    data = request.json
    filepath = data.get('filepath')

    if filepath in streams:
        stream = streams.pop(filepath)
        stream.stop()
        stream.close()

        wait_handles = [stream.increase_volume() for stream in streams.values()]
        for handle in wait_handles:
            handle.wait()
        return jsonify({"status": "Playback stopped for " + filepath}), 200
    else:
        return jsonify({"status": "No playback to stop for " + filepath}), 404


@app.route('/stop-all', methods=['PUT'])
def stop_all():
    global streams

    for stream in list(streams.values()):
        stream.stop()
        stream.close()

    streams.clear()

    return jsonify({"status": "All playbacks stopped"}), 200


@app.route('/fade-all-sounds', methods=['PUT'])
def fade_all_sounds():
    wait_handles = [stream.decrease_volume() for stream in streams.values()]
    for handle in wait_handles:
        handle.wait()

    return jsonify({"status": "Volume decreased for all streams"}), 200


@app.route('/amplify-all-sounds', methods=['PUT'])
def amplify_all_sounds():
    wait_handles = [stream.increase_volume() for stream in streams.values()]
    for handle in wait_handles:
        handle.wait()

    return jsonify({"status": "Volume increased for all streams"}), 200


@app.route('/volume', methods=['POST'])
def set_volume():
    data = request.json
    filepath = data.get('filepath')
    new_volume = float(data.get('volume'))

    if filepath in streams:
        streams[filepath].set_volume(new_volume)
        return jsonify({"status": "Volume adjusted for " + filepath, "new_volume": new_volume}), 200
    else:
        return jsonify({"status": "No active playback for " + filepath}), 404


def get_output_stream():
    global output_stream
    if 'output_stream' not in globals() or output_stream is None or output_stream.closed:
        output_stream = sd.OutputStream(callback=audio_callback, samplerate=44100, channels=2)
        output_stream.start()
    return output_stream


if __name__ == '__main__':
    get_output_stream()
    app.run(debug=True)
