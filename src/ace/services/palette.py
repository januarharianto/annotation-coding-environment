"""Colour palette for annotation codes.

Uses golden-angle hue spacing with alternating lightness bands to generate
visually distinct colours that scale to 36+ codes.
"""

import colorsys


def _generate_palette(n: int) -> list[tuple[str, str]]:
    golden_ratio = 0.618033988749895
    colours = []
    for i in range(n):
        hue = (i * golden_ratio) % 1.0
        lightness = 0.42 if i % 2 == 0 else 0.58
        saturation = 0.65
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        hex_val = f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"
        colours.append((hex_val, f"Colour {i + 1}"))
    return colours


COLOUR_PALETTE = _generate_palette(36)


def next_colour(existing_count: int) -> str:
    """Return the next colour from the palette, cycling if needed."""
    return COLOUR_PALETTE[existing_count % len(COLOUR_PALETTE)][0]
