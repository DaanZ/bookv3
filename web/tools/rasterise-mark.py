"""Turn the mark's SVG sources into the PNGs and the Windows icon.

Called by `export-mark.mjs`, which writes the sources; not meant to be run on its own.

    python rasterise-mark.py <folder of sources> <repo root>

Each size is rendered from the source drawn for it rather than scaled down from the
largest, because the page count changes with size: a 16px icon made by shrinking the
512px one would carry five pages in sixteen pixels, which is a smudge.
"""

import io
import sys
from pathlib import Path

import cairosvg
from PIL import Image

# Which drawing each size gets. The breakpoints are the design: the S alone below 32,
# one page from 32, five from 128.
def source_for(size):
    if size < 32:
        return "bare.svg"
    if size < 128:
        return "small.svg"
    return "icon.svg"


def render(svg_path, size):
    png = cairosvg.svg2png(url=str(svg_path), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main():
    sources = Path(sys.argv[1])
    repo = Path(sys.argv[2])
    public = repo / "web" / "public" / "assets"

    for size in (16, 32, 64, 180, 512):
        render(sources / source_for(size), size).save(public / f"favicon-{size}.png")

    ico_sizes = (16, 24, 32, 48, 64, 128, 256)
    images = [render(sources / source_for(size), size) for size in ico_sizes]
    images[-1].save(
        repo / "assets" / "bookv3.ico",
        sizes=[(size, size) for size in ico_sizes],
        append_images=images[:-1],
    )

    render(sources / "tray.svg", 64).save(repo / "assets" / "tray-mark.png")


if __name__ == "__main__":
    main()
