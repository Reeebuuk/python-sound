import numpy as np
import sounddevice as sd

from globals import streams


class InputOutputAudioStream:
    def __init__(self, input_device_index, output_device_index, fade_background_music, volume=1.0, sample_rate=44100):
        self.input_stream = sd.InputStream(
            device=input_device_index,
            samplerate=sample_rate,
            channels=1,
            callback=self.input_callback
        )
        self.output_stream = sd.OutputStream(
            device=output_device_index,
            samplerate=sample_rate,
            channels=2,
            callback=self.output_callback
        )
        self.fade_background_music = fade_background_music
        self.input_device_index = input_device_index
        self.output_device_index = output_device_index
        self.volume = volume
        self.sample_rate = sample_rate
        self.buffer = np.zeros((1024, 2), dtype='float32')
        self.buffer_index = 0

    def start_streams(self):
        try:
            self.input_stream.start()
            self.output_stream.start()
        except Exception as e:
            print("Error in starting streams:", e)

    def input_callback(self, indata, frames, time, status):
        if status:
            print("Input stream error:", status)
        # Process the input data and store in buffer
        volume_adjusted_data = indata * self.volume
        end_index = self.buffer_index + len(indata)
        if end_index <= len(self.buffer):
            self.buffer[self.buffer_index:end_index] = volume_adjusted_data
            self.buffer_index = end_index % len(self.buffer)

    def output_callback(self, outdata, frames, time, status):
        if status:
            print("Output stream error:", status)
        # Provide data from the buffer to the output
        start_index = self.buffer_index - frames
        if start_index < 0:
            outdata[:] = np.concatenate((self.buffer[start_index:], self.buffer[:self.buffer_index]))
        else:
            outdata[:] = self.buffer[start_index:self.buffer_index]
        self.buffer_index = (self.buffer_index - frames) % len(self.buffer)

    def stop_streams(self):
        if self.input_stream.active or self.output_stream.active:
            self.input_stream.stop()
            self.input_stream.close()
            self.output_stream.stop()
            self.output_stream.close()

        if self.fade_background_music:
            wait_handles = [stream.increase_volume() for stream in streams.values()]
            for handle in wait_handles:
                handle.wait()

        print("Streams stopped and closed.")
