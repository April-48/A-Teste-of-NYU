"""Shared blue-orange chart family and a single linked-selection color.

Scatter hues classify benchmark relation; heatmap/map lightness encodes share.
Dark navy marks selection across views, independently of either statistic.
"""
ABOVE = "#086b9f"
BELOW = "#b94708"
SMALL_SAMPLE = "#536b79"
BAR_BACKGROUND = "#7aaac6"
SELECTED = "#173f59"

# Two-hue sequential scale: light blue (low) to burnt orange (high).
# CIELAB interpolation keeps lightness ordered; no midpoint or benchmark is implied.
HEAT_COLORS = [[0.0, '#d4ecff'], [0.0625, '#d3dfee'], [0.125, '#d2d2dc'], [0.1875, '#d0c6cb'], [0.25, '#cdb9ba'], [0.3125, '#caadaa'], [0.375, '#c7a19a'], [0.4375, '#c3948a'], [0.5, '#be887a'], [0.5625, '#b97c6a'], [0.625, '#b4705b'], [0.6875, '#ae644c'], [0.75, '#a7583e'], [0.8125, '#a14c2f'], [0.875, '#994021'], [0.9375, '#923311'], [1.0, '#8a2500']]
