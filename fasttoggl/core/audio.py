import ctypes
import ctypes.util
import os
import sys
import threading
import wave
from contextlib import contextmanager

import pyaudio


def record_audio(
    output_file: str,
    duration: float = None,
    sample_rate: int = 44100,
    channels: int = 1,
    chunk_size: int = 1024,
) -> bytes:
    os.environ.setdefault("JACK_NO_START_SERVER", "1")
    with _suppress_audio_backend_logs():
        p = pyaudio.PyAudio()

    try:
        with _suppress_audio_backend_logs():
            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                frames_per_buffer=chunk_size,
            )

        print(f"Recording audio to {output_file}...")
        print("Press Enter to stop recording")

        frames = []

        try:
            if duration:
                for i in range(0, int(sample_rate / chunk_size * duration)):
                    data = stream.read(chunk_size)
                    frames.append(data)
                    print(
                        f"\rRecording... {i * chunk_size / sample_rate:.1f}s / {duration}s",
                        end="",
                        flush=True,
                    )
                print()
            else:
                stop_event = threading.Event()
                stopper = threading.Thread(
                    target=_wait_for_enter, args=(stop_event,), daemon=True
                )
                stopper.start()
                while not stop_event.is_set():
                    data = stream.read(chunk_size)
                    frames.append(data)
                    print(
                        f"\rRecording... {len(frames) * chunk_size / sample_rate:.1f}s",
                        end="",
                        flush=True,
                    )

        except KeyboardInterrupt:
            print("\nRecording stopped")

        stream.stop_stream()
        stream.close()

        wf = wave.open(output_file, "wb")
        wf.setnchannels(channels)
        wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))
        wf.close()

        print(f"\nAudio saved to {output_file}")
        return b"".join(frames)
    except Exception as e:
        print(f"Error recording audio: {e}")
        sys.exit(1)
    finally:
        p.terminate()


@contextmanager
def _suppress_audio_backend_logs():
    err_handler = _alsa_error_handler()
    asound = None
    try:
        lib = ctypes.util.find_library("asound")
        if lib:
            asound = ctypes.cdll.LoadLibrary(lib)
            asound.snd_lib_error_set_handler(err_handler)
    except Exception:
        asound = None
    stderr_fd = sys.stderr.fileno()
    saved_stderr_fd = os.dup(stderr_fd)
    try:
        with open(os.devnull, "w") as devnull:
            os.dup2(devnull.fileno(), stderr_fd)
            yield
    finally:
        try:
            os.dup2(saved_stderr_fd, stderr_fd)
            os.close(saved_stderr_fd)
        finally:
            if asound is not None:
                try:
                    asound.snd_lib_error_set_handler(ctypes.c_void_p())
                except Exception:
                    pass


def _alsa_error_handler():
    CALLBACK = ctypes.CFUNCTYPE(
        None,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
    )

    def py_error_handler(filename, line, function, err, fmt):
        return None

    return CALLBACK(py_error_handler)


def _wait_for_enter(stop_event: threading.Event):
    try:
        input()
    except Exception:
        pass
    stop_event.set()
