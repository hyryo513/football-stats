"""Device selection logic: MPS → CUDA → CPU."""

import torch

device: str = (
    "mps"
    if torch.backends.mps.is_available()
    else "cuda"
    if torch.cuda.is_available()
    else "cpu"
)

__all__ = ["device"]
