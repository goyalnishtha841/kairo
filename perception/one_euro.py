"""One-Euro filter (Casiez et al. 2012): low lag when moving fast, low jitter when still."""
import math

import numpy as np


def _alpha(cutoff, dt):
    tau = 1.0 / (2 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuro:
    """Vectorised filter over an array of any shape (e.g. 21x3 landmarks)."""

    # defaults tuned for normalised image coords (speeds ~0.1-2 units/s)
    def __init__(self, min_cutoff=1.5, beta=8.0, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = None
        self.dx_prev = None
        self.t_prev = None

    def reset(self):
        self.x_prev = self.dx_prev = self.t_prev = None

    def __call__(self, x, t):
        x = np.asarray(x, dtype=np.float64)
        if self.x_prev is None:
            self.x_prev, self.dx_prev, self.t_prev = x, np.zeros_like(x), t
            return x
        dt = max(t - self.t_prev, 1e-6)
        dx = (x - self.x_prev) / dt
        a_d = _alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * np.abs(dx_hat)
        a = 1.0 / (1.0 + (1.0 / (2 * math.pi * cutoff)) / dt)
        x_hat = a * x + (1 - a) * self.x_prev
        self.x_prev, self.dx_prev, self.t_prev = x_hat, dx_hat, t
        return x_hat
