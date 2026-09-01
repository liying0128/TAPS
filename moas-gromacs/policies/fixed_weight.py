"""Static weight modes: equal, LAST-dominant, kinetic, commitment, information."""

WEIGHT_MODES = {
    "equal": dict(novelty=1, boundary=1, kinetic=1, uncertainty=1, commitment=1, information_gain=1),
    "last_dominant": dict(novelty=2, boundary=2, kinetic=0, uncertainty=0, commitment=0, information_gain=0),
    "kinetic_dominant": dict(novelty=0, boundary=0, kinetic=2, uncertainty=1, commitment=0, information_gain=0),
    "commitment_dominant": dict(novelty=0, boundary=0, kinetic=0, uncertainty=0, commitment=2, information_gain=0),
    "information_dominant": dict(novelty=0, boundary=0, kinetic=1, uncertainty=0, commitment=0, information_gain=2),
}
