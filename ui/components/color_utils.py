"""Color utility functions."""

def interpolate_color(color1, color2, factor):
    """Interpolate between two hex colors."""
    try:
        c1 = [int(color1[i : i + 2], 16) for i in (1, 3, 5)]
        c2 = [int(color2[i : i + 2], 16) for i in (1, 3, 5)]
        new_color = [int(c1[i] + (c2[i] - c1[i]) * factor) for i in range(3)]
        return f"#{new_color[0]:02x}{new_color[1]:02x}{new_color[2]:02x}"
    except Exception:  # pylint: disable=broad-exception-caught
        return color1


def lighten_color(hex_color, percent=10):
    """Lighten a hex color by a percentage (0-100)."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        factor = percent / 100
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:  # pylint: disable=broad-exception-caught
        return hex_color


def darken_color(hex_color, percent=10):
    """Darken a hex color by a percentage (0-100)."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        factor = 1 - (percent / 100)
        r = max(0, int(r * factor))
        g = max(0, int(g * factor))
        b = max(0, int(b * factor))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:  # pylint: disable=broad-exception-caught
        return hex_color
