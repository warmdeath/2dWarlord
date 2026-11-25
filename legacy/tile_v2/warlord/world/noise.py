"""Vectorised value noise (numpy) — fast enough to generate a 12-million-tile world in seconds."""
import numpy as np

P = 1024


def _table(seed, shape):
    rng = np.random.default_rng(seed)
    return rng.random(shape, dtype=np.float32)


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


def noise1(xs, freq, seed):
    t = _table(seed, P)
    f = xs * freq
    i = np.floor(f).astype(np.int64)
    fr = _smooth((f - i).astype(np.float32))
    a = t[i % P]
    b = t[(i + 1) % P]
    return a + (b - a) * fr


def fbm1(xs, freq, seed, octaves=4, gain=0.5):
    total = np.zeros_like(xs, dtype=np.float32)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        total += noise1(xs, freq * (2 ** o), seed + o * 101) * amp
        norm += amp
        amp *= gain
    return total / norm


def noise2(xs, ys, fx, fy, seed):
    """xs shape (W,1), ys shape (1,H) -> (W,H)."""
    t = _table(seed, (P, P))
    gx = xs * fx
    gy = ys * fy
    ix = np.floor(gx).astype(np.int64)
    iy = np.floor(gy).astype(np.int64)
    tx = _smooth((gx - ix).astype(np.float32))
    ty = _smooth((gy - iy).astype(np.float32))
    ix0, ix1 = ix % P, (ix + 1) % P
    iy0, iy1 = iy % P, (iy + 1) % P
    a = t[ix0, iy0]
    b = t[ix1, iy0]
    c = t[ix0, iy1]
    d = t[ix1, iy1]
    top = a + (b - a) * tx
    bot = c + (d - c) * tx
    return top + (bot - top) * ty


def fbm2(xs, ys, fx, fy, seed, octaves=3, gain=0.5):
    total = None
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        n = noise2(xs, ys, fx * (2 ** o), fy * (2 ** o), seed + o * 977) * amp
        total = n if total is None else total + n
        norm += amp
        amp *= gain
    return total / norm


def smooth_array(a, width):
    """Moving-average smoothing of a 1D array (edge padded)."""
    if width <= 1:
        return a.astype(np.float32)
    pad = width // 2
    p = np.pad(a.astype(np.float64), (pad, pad), mode="edge")
    c = np.cumsum(np.insert(p, 0, 0.0))
    out = (c[width:] - c[:-width]) / width
    return out[: len(a)].astype(np.float32)
