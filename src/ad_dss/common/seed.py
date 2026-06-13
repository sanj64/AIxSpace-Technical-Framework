import os
import random

import numpy as np


def set_seed(seed: int = 42) -> None:
    """Seed all RNGs for reproducibility. TF seeded lazily on first import."""
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import tensorflow as tf

        tf.random.set_seed(seed)
    except ImportError:
        pass
