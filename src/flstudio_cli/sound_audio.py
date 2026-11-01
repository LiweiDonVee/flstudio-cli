"""Small PCM comparisons for sound-design decisions, never a taste score."""
from __future__ import annotations

from pathlib import Path
import math
import wave


def _numpy():
    try:
        import numpy
    except ImportError:
        raise ValueError('Sound analysis requires the sound-design extra: uv pip install "flstudio-cli[sound-design]"') from None
    return numpy


def load(path):
    np = _numpy()
    with wave.open(str(path), 'rb') as stream:
        rate, channels, width = stream.getframerate(), stream.getnchannels(), stream.getsampwidth()
        frames = stream.getnframes()
        raw = stream.readframes(frames)
    if len(raw) != frames * channels * width or not frames:
        raise ValueError('Expected a complete, nonempty PCM WAV')
    if width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128) / 128
    elif width in (2, 4):
        data = np.frombuffer(raw, dtype='<i2' if width == 2 else '<i4').astype(np.float64) / 2**(width*8-1)
    elif width == 3:
        octets = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        signed = octets[:, 0] | octets[:, 1] << 8 | octets[:, 2] << 16
        data = ((signed ^ 0x800000) - 0x800000).astype(np.float64) / 8388608
    else:
        raise ValueError('Sound analysis accepts integer PCM WAV (8/16/24/32-bit)')
    return rate, data.reshape(-1, channels)


def _db(value):
    return round(20 * math.log10(max(float(value), 1e-12)), 5)


def _spectrum(rate, data):
    np = _numpy()
    # Average channel power rather than summing channels: out-of-phase stereo
    # must not disappear from a brightness or masking observation.
    size, hop = 2048, 1024
    if len(data) < size:
        data = np.pad(data, ((0, size - len(data)), (0, 0)))
    windows = np.lib.stride_tricks.sliding_window_view(data, size, axis=0)[::hop]
    power = (np.abs(np.fft.rfft(windows * np.hanning(size), axis=-1))**2).mean(axis=1)
    return np.fft.rfftfreq(size, 1/rate), power


BANDS = ((20, 120), (120, 350), (350, 2000), (2000, 6000), (6000, 20000))


def analyze(path: Path):
    np = _numpy()
    rate, signal = load(path)
    peak = float(np.max(np.abs(signal)))
    rms = float(np.sqrt(np.mean(signal**2)))
    frequencies, power = _spectrum(rate, signal)
    profile = power.mean(axis=0)
    total = float(profile.sum())
    fractions = [float(profile[(frequencies >= low) & (frequencies < high)].sum() / max(total, 1e-30))
                 for low, high in BANDS]
    frame = max(1, round(rate * .01))
    envelope = np.sqrt(np.mean(np.pad(signal, ((0, (-len(signal)) % frame), (0, 0)))
                             .reshape(-1, frame, signal.shape[1])**2, axis=(1, 2)))
    active = np.flatnonzero(envelope > max(float(envelope.max()) * .1, 1e-6))
    stereo = {}
    if signal.shape[1] == 2:
        left, right = signal[:, 0], signal[:, 1]
        denom = float(np.sqrt(np.sum(left**2) * np.sum(right**2)))
        mid, side = (left + right)/2, (left-right)/2
        stereo = {'correlation': float(np.sum(left*right)/denom) if denom else None,
                  'side_to_mid_db': _db(np.sqrt(np.mean(side**2))) - _db(np.sqrt(np.mean(mid**2))),
                  'mono_rms_dbfs': _db(np.sqrt(np.mean(mid**2)))}
    return {'path': str(Path(path).resolve()), 'sample_rate': rate, 'channels': signal.shape[1],
            'duration_seconds': len(signal)/rate, 'peak_dbfs': _db(peak), 'rms_dbfs': _db(rms),
            'sample_peak_count': int(np.count_nonzero(np.abs(signal) >= .9999)),
            'silent': peak < 1e-8, 'crest_db': _db(peak) - _db(rms),
            'spectral_centroid_hz': float(np.sum(frequencies*profile)/total) if total else 0,
            'band_energy_fraction': {f'{lo}-{hi}Hz': value for (lo, hi), value in zip(BANDS, fractions)},
            'active_window_seconds': [float(active[0])*.01, min(len(signal)/rate, (float(active[-1])+1)*.01)] if len(active) else None,
            'stereo': stereo,
            'interpretation': 'Signal observations, not listening or an aesthetic score; centroid depends on notes, level and mechanism.'}


def compare(left: Path, right: Path, *, tail_tolerance_seconds=.02):
    np = _numpy()
    rate_a, a = load(left)
    rate_b, b = load(right)
    duration_delta=abs(len(a)/rate_a-len(b)/rate_b)
    if not math.isfinite(tail_tolerance_seconds) or not 0<=tail_tolerance_seconds<=.5:
        raise ValueError('Tail comparison tolerance must be within 0..0.5 seconds')
    if rate_a != rate_b or a.shape[1]!=b.shape[1] or duration_delta>tail_tolerance_seconds:
        return {'comparable': False, 'reason': 'PCM rate, channels or frame count differ',
                'left_shape': list(a.shape), 'right_shape': list(b.shape),'duration_difference_seconds':duration_delta}
    same_shape=a.shape==b.shape
    if not same_shape:
        # FL's leave-tail renderer can end a few milliseconds differently
        # between stochastic instances. Compare from the same start, retaining
        # the extra tail by zero-padding only the analysis array.
        count=max(len(a),len(b))
        a=np.pad(a,((0,count-len(a)),(0,0)))
        b=np.pad(b,((0,count-len(b)),(0,0)))
    delta = a-b
    _, pa = _spectrum(rate_a, a)
    _, pb = _spectrum(rate_b, b)
    sa, sb = pa.mean(axis=0), pb.mean(axis=0)
    norm = float(np.linalg.norm(sa)*np.linalg.norm(sb))
    rms_a, rms_b = float(np.sqrt(np.mean(a*a))), float(np.sqrt(np.mean(b*b)))
    return {'comparable': True, 'pcm_equal': bool(same_shape and np.array_equal(a, b)),
            'duration_difference_seconds':duration_delta,
            'analysis_alignment':'same start; short variable tail zero-padded for analysis only' if not same_shape else 'unaltered equal frames',
            'duration_tolerance_seconds':tail_tolerance_seconds,
            'difference_rms': float(np.sqrt(np.mean(delta**2))),
            'relative_difference_rms': float(np.sqrt(np.mean(delta**2)) / max(rms_a, 1e-12)),
            'rms_difference_db': abs(_db(rms_a)-_db(rms_b)),
            'spectral_cosine_distance': max(0., 1.-float(np.dot(sa,sb)/norm)) if norm else (0. if not sa.any() and not sb.any() else 1.),
            'interpretation': 'Exact PCM comparison plus repeatability proxies; these do not certify perceptual equivalence.'}


def overlap(solo: Path, accompaniment: Path, window_seconds=None):
    np = _numpy()
    rate, a = load(solo)
    other_rate, b = load(accompaniment)
    if rate != other_rate or a.shape[1]!=b.shape[1]:
        return {'available': False, 'reason': 'Aligned WAVs with equal rate/channels/frames required'}
    if window_seconds is not None:
        if not math.isfinite(window_seconds) or window_seconds<=0:
            raise ValueError('Context occupancy window must be finite and positive')
        count=round(window_seconds*rate)
        if min(len(a),len(b))+round(.02*rate)<count:
            return {'available':False,'reason':'One render ends before the fixed musical excerpt window'}
        a=np.pad(a[:count],((0,max(0,count-len(a))),(0,0)))
        b=np.pad(b[:count],((0,max(0,count-len(b))),(0,0)))
    elif abs(len(a)-len(b))/rate>.02:
        return {'available':False,'reason':'Different tails: supply the task musical duration to compare its fixed context window'}
    elif a.shape!=b.shape:
        count=max(len(a),len(b))
        a=np.pad(a,((0,count-len(a)),(0,0)))
        b=np.pad(b,((0,count-len(b)),(0,0)))
    frequencies, pa = _spectrum(rate, a)
    _, pb = _spectrum(rate, b)
    rows = []
    for low, high in BANDS:
        mask = (frequencies >= low) & (frequencies < high)
        ea, eb = pa[:, mask].sum(axis=1), pb[:, mask].sum(axis=1)
        active = ea > max(float(ea.max())*.01, 1e-20)
        rows.append({'band_hz': [low, high],
                     'target_to_rest_db': float(10*np.log10(max(float(ea[active].sum()),1e-30)/max(float(eb[active].sum()),1e-30))) if active.any() else None,
                     'concurrent_energy_fraction': float(np.minimum(ea,eb).sum()/max(float(ea.sum()),1e-30))})
    return {'available': True, 'bands': rows,'analysis_window_seconds':len(a)/rate,
            'interpretation': 'Concurrent band occupancy during the exact phrase. Not psychoacoustic masking, source separation, or mix quality; inspect attacks, notes and musical roles too.'}


def matched_previews(paths: list[Path], output: Path, measurement_seconds=None):
    """Apply one constant gain per file, preserving raw files and dynamics."""
    np = _numpy()
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Choose a new preview directory with an existing parent')
    loaded = [load(path) for path in paths]
    if measurement_seconds is not None and (not math.isfinite(measurement_seconds) or measurement_seconds<=0):
        raise ValueError('Preview measurement window must be finite and positive')
    rms = [float(np.sqrt(np.mean((signal[:round(rate*measurement_seconds)] if measurement_seconds else signal)**2)))
           for rate, signal in loaded]
    if any(value < 1e-8 for value in rms):
        raise ValueError('Cannot loudness-match a silent candidate; fix it or omit it explicitly')
    reference = min(.1, min(rms))
    largest_peak = max(float(np.max(np.abs(signal)))*reference/value for (_, signal), value in zip(loaded, rms))
    if largest_peak > .89:
        reference *= .89/largest_peak
    output.mkdir()
    rows = []
    for index, (source, (rate, signal), value) in enumerate(zip(paths, loaded, rms)):
        gain = reference/value
        target = output/f'{index+1:02d}-{source.parent.name}-{source.stem}.wav'
        samples = np.rint(np.clip(signal*gain, -1, 1-1/32768)*32768).astype('<i2')
        with wave.open(str(target), 'wb') as stream:
            stream.setparams((signal.shape[1], 2, rate, len(signal), 'NONE', 'not compressed'))
            stream.writeframes(samples.tobytes())
        rows.append({'source': str(source.resolve()), 'preview': str(target.resolve()),
                     'gain_db': _db(gain), 'rms_dbfs': _db(reference), 'raw_audio_preserved': True})
    return {'method': 'Equal integrated PCM RMS, peak-constrained common reference; not LUFS or perceived-loudness equality',
            'target_rms_dbfs': _db(reference), 'measurement_window_seconds':measurement_seconds,'files': rows}
