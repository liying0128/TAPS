"""Rule-based dynamic weights from sampling stage (early / middle / late)."""

STAGE_WEIGHTS = {
    "early": dict(novelty=2, boundary=2, kinetic=0.5, uncertainty=0.5, commitment=0, information_gain=0),
    "middle": dict(novelty=0.5, boundary=0.5, kinetic=2, uncertainty=2, commitment=0.5, information_gain=0.5),
    "late": dict(novelty=0.25, boundary=0.25, kinetic=0.5, uncertainty=0.5, commitment=2, information_gain=2),
}


def weights_from_state(stage: str) -> dict:
    if stage not in STAGE_WEIGHTS:
        raise KeyError(stage)
    return dict(STAGE_WEIGHTS[stage])


def stage_by_time_rank(t_ps) -> list:
    """Tertile of time within the evaluation slice: early / middle / late."""
    import numpy as np

    t = np.asarray(t_ps, dtype=np.float64)
    q1, q2 = np.quantile(t, [1.0 / 3.0, 2.0 / 3.0])
    out = []
    for x in t:
        if x <= q1:
            out.append("early")
        elif x <= q2:
            out.append("middle")
        else:
            out.append("late")
    return out
