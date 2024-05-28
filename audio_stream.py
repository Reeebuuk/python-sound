import numpy as np
import soundfile as sf
import threading
import time
from fractions import Fraction
from scipy.signal import resample_poly

from globals import streams


class AudioStream:
    def __init__(self, filepath, loop=False, volume=1.0, background_volume=0.3, target_samplerate=48000):
        self.filepath = filepath
        self.loop = loop
        self.volume = volume
        self.original_volume = volume
        self.background_volume = background_volume
        self.target_samplerate = target_samplerate

        # Load the audio file
        self.audio_data, self.samplerate = sf.read(filepath, dtype='float32')

        # Resample audio if necessary
        if self.samplerate != self.target_samplerate:
            ratio = Fraction(self.target_samplerate, self.samplerate)
            self.audio_data = resample_poly(self.audio_data, up=ratio.numerator, down=ratio.denominator)
            self.samplerate = self.target_samplerate

        self.position = 0
        self.is_playing = True
        self.volume_change_complete = threading.Event()  # Event to signal completion of volume change

        if self.audio_data.ndim == 1:
            self.audio_data = np.column_stack((self.audio_data, self.audio_data))

            # Print audio file details
        channels = 2 if self.audio_data.ndim > 1 else 1
        print(f"File loaded: {filepath}")
        print(f"Sample rate: {self.samplerate} Hz (resampled)")
        print(f"Channels: {channels}")
        print(f"Total frames: {len(self.audio_data)}")
        print(f"Duration: {len(self.audio_data) / self.samplerate:.2f} seconds")

    def read(self, frames):
        if not self.is_playing:
            return np.zeros((frames, 2))  # Return silence if not playing

        end_idx = self.position + frames
        result = np.zeros((frames, 2))  # Ensure there's always a result array

        if end_idx < len(self.audio_data):
            result = self.audio_data[self.position:end_idx] * self.volume
            self.position = end_idx
        else:
            # Handle end of data
            remaining_frames = len(self.audio_data) - self.position
            result[:remaining_frames] = self.audio_data[self.position:] * self.volume
            if self.loop:
                self.position = 0  # Reset position for looping
            else:
                self.is_playing = False  # Set to not playing
                self.position = len(self.audio_data)  # Ensure position is at the end
                self.on_playback_end()  # Trigger any end-of-playback logic

        return result

    def stop(self):
        self.is_playing = False

    def start_volume_ramp(self, target_vol, duration):
        def update_volume():
            nonlocal start_time
            current_time = time.time()
            elapsed_time = current_time - start_time

            if elapsed_time < duration:
                self.volume += (target_vol - self.volume) * (elapsed_time / duration)
                threading.Timer(0.1, update_volume).start()
            else:
                self.volume = target_vol
                self.volume_change_complete.set()

        print(f"Change volume for {self.filepath} to {target_vol}")
        self.volume_change_complete.clear()  # Clear the event before starting
        start_time = time.time()
        update_volume()

    def decrease_volume(self):
        self.start_volume_ramp(self.background_volume, 1)
        return self.volume_change_complete

    def increase_volume(self):
        self.start_volume_ramp(self.original_volume, 1)
        return self.volume_change_complete

    def set_volume(self, volume):
        self.start_volume_ramp(volume, 1)
        return self.volume_change_complete

    def on_playback_end(self):
        if not self.loop:
            global streams
            for filepath, stream in streams.items():
                if stream.loop and stream.is_playing:
                    stream.increase_volume()

    def close(self):
        self.stop()
        print("AudioStream has been closed and resources have been cleaned up.")
