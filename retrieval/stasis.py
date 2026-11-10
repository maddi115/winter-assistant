"""Probability Stasis gate (from maddis-probability-stasisv2, v8.1).

stability  = how tightly the top results agree with each other (0..1)
confidence = how close the top results are to the question (0..1)
The softmax temperature is auto-tuned (binary search) toward stability 0.80.
If stability or confidence is too low, Winter says "idk" instead of answering.
"""
import numpy as np


def softmax(x, temp=1.0):
    x = np.asarray(x, dtype=np.float32) / max(1e-6, float(temp))
    x = x - x.max()
    ex = np.exp(x)
    return ex / (ex.sum() + 1e-9)


def stasis_metrics(nbh_vecs: np.ndarray, sims: np.ndarray, temp: float):
    w = softmax(sims, temp)
    centroid = (w[:, None] * nbh_vecs).sum(axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-9)
    stability = float((w * (nbh_vecs @ centroid)).sum())
    confidence = float((w * sims).sum())
    return stability, confidence


def autotune(nbh_vecs, sims, target=0.80, tol=0.05, steps=8, init_temp=0.85):
    temp, low, high = float(init_temp), 0.20, 2.50
    stab, conf = stasis_metrics(nbh_vecs, sims, temp)
    for _ in range(steps):
        stab, conf = stasis_metrics(nbh_vecs, sims, temp)
        if abs(stab - target) <= tol:
            break
        if stab < target:
            high = temp
            temp = (temp + low) / 2
        else:
            low = temp
            temp = (temp + high) / 2
    return stab, conf, temp


def gate(nbh_vecs, sims, has_keyword: bool, stability_min=0.60, confidence_min=0.45):
    """Returns (passed, stability, confidence)."""
    if len(sims) == 0:
        return False, 0.0, 0.0
    stab, conf, _ = autotune(np.asarray(nbh_vecs), np.asarray(sims, dtype=np.float32))
    if has_keyword:                       # stasisv2 keyword boost
        conf = min(conf * 1.25, 0.95)
    return (stab >= stability_min and conf >= confidence_min), stab, conf
