from math import floor

import numpy as np


# Define the number of chunks
def get_page_chunks(pages, num_chunks: int = 10):
    amount_pages: int = len(pages)
    # Define the range of the left side of the Gaussian distribution (0 to 1)
    x = np.linspace(0, 1, 1000)

    # Compute the Gaussian probability density function (normalized)
    mean = 0
    std_dev = 1
    gaussian_pdf = (1 / (std_dev * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / std_dev) ** 2)

    # Calculate the cumulative distribution function (CDF)
    gaussian_cdf = np.cumsum(gaussian_pdf)
    gaussian_cdf /= gaussian_cdf[-1]  # Normalize the CDF to [0, 1]

    # Divide the CDF into 10 equal probability chunks and find the corresponding x ranges
    chunk_edges = np.linspace(0, 1, num_chunks + 1)
    chunk_ranges = []

    for i in range(num_chunks):
        lower_bound = chunk_edges[i]
        upper_bound = chunk_edges[i + 1]
        lower_x = x[np.searchsorted(gaussian_cdf, lower_bound)]
        upper_x = x[np.searchsorted(gaussian_cdf, upper_bound)]
        chunk_ranges.append((lower_x, upper_x))

    page_chunks = []
    for chunk in chunk_ranges:
        start_index = floor(chunk[0]*amount_pages)
        end_index = floor(chunk[1]*amount_pages)
        page_chunks.append(pages[start_index:end_index])
    return page_chunks


if __name__ == "__main__":
    page_chunks = get_page_chunks()
    for page_chunk in page_chunks:
        print(page_chunk)
