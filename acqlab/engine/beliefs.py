"""Walk-away distribution under uncertain parameters."""
import numpy as np

from acqlab.engine.model import PARAM_NAMES, Deal, Params
from acqlab.engine.walkaway import walk_away

Beliefs = dict[str, tuple[float, float]]  # param name -> (low, high), sampled uniformly


def sample_params(base: Params, beliefs: Beliefs, n: int, rng: np.random.Generator) -> list[Params]:
    unknown = set(beliefs) - set(PARAM_NAMES)
    if unknown:
        raise ValueError(f"unknown parameters: {sorted(unknown)}")
    draws = {k: rng.uniform(*beliefs[k], n) for k in sorted(beliefs)}
    return [Params.model_validate({**base.model_dump(), **{k: float(v[i]) for k, v in draws.items()}})
            for i in range(n)]


def evaluate_under(deal: Deal, base: Params, beliefs: Beliefs, n: int = 200, seed: int = 0) -> np.ndarray:
    """Monte Carlo walk-away prices. Params not in beliefs stay at their base value."""
    rng = np.random.default_rng(seed)
    return np.array([walk_away(deal, p) for p in sample_params(base, beliefs, n, rng)])
