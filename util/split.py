"""Where a book is cut into parts.

This lived inside `chunks.py`, which cannot be imported without an API key. The cost
estimator needs the same boundaries to price a book *before* any key is used, and two
copies of this arithmetic would drift, so the maths moved here and `chunks.py` calls it.

The split is deliberately uneven: chunk edges are equal-probability slices of the left
half of a Gaussian CDF, so parts are dense near the front of the book and widen toward
the end. The reader's front-weighted progress bar is the other half of the same idea.
"""

from math import floor

import numpy as np


def page_chunk_bounds(page_count: int, num_chunks: int = 10):
    """Return `[(start, end), ...]` page indices, contiguous and covering every page."""
    # Define the range of the left side of the Gaussian distribution (0 to 1)
    x = np.linspace(0, 1, 1000)

    # Compute the Gaussian probability density function (normalized)
    mean = 0
    std_dev = 1
    gaussian_pdf = (1 / (std_dev * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / std_dev) ** 2)

    # Calculate the cumulative distribution function (CDF)
    gaussian_cdf = np.cumsum(gaussian_pdf)
    gaussian_cdf /= gaussian_cdf[-1]  # Normalize the CDF to [0, 1]

    # Divide the CDF into equal probability chunks and find the corresponding x ranges
    chunk_edges = np.linspace(0, 1, num_chunks + 1)

    bounds = []
    for index in range(num_chunks):
        lower_x = x[np.searchsorted(gaussian_cdf, chunk_edges[index])]
        upper_x = x[np.searchsorted(gaussian_cdf, chunk_edges[index + 1])]
        bounds.append((floor(lower_x * page_count), floor(upper_x * page_count)))
    return bounds
