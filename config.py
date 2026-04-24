"""Default configuration values."""

# iOS semantic dimensions based on Dynamic Island iPhone models.
STATUSBAR_HEIGHT = 54
NAVBAR_HEIGHT = 44
TABBAR_HEIGHT = 49
SAFE_AREA_BOTTOM = 34

# Default crop values assuming both a navigation bar and a tab bar.
TOP_CROP = STATUSBAR_HEIGHT + NAVBAR_HEIGHT  # 98
BOTTOM_CROP = TABBAR_HEIGHT + SAFE_AREA_BOTTOM  # 83

# Backward-compatible aliases for older external imports.
top_crop = TOP_CROP
bottom_crop = BOTTOM_CROP

# Horizontal edge crop used to suppress scroll indicators and noisy margins.
X_MARGIN = 40
# Base template height used during overlap matching.
TEMPLATE_HEIGHT = 200
# Confidence threshold for accepting overlap matches.
THRESHOLD = 0.6
