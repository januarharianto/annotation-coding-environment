"""Colourblind-accessible colour palette for annotation codes."""

COLOUR_PALETTE = [
    ("#E69F00", "Orange"),
    ("#56B4E9", "Sky blue"),
    ("#009E73", "Teal"),
    ("#F0E442", "Yellow"),
    ("#0072B2", "Blue"),
    ("#D55E00", "Red-orange"),
    ("#CC79A7", "Pink"),
    ("#999999", "Grey"),
    ("#332288", "Indigo"),
    ("#44AA99", "Cyan"),
]


def next_colour(existing_count: int) -> str:
    """Return the next colour from the palette, cycling if needed."""
    return COLOUR_PALETTE[existing_count % len(COLOUR_PALETTE)][0]
