"""Generate lightweight showcase preview assets for README files."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = REPO_ROOT / "examples" / "cases"

INPUT_WIDTH = 220
STITCHED_WIDTH = 220
PADDING = 16
LABEL_HEIGHT = 36
BG_COLOR = (248, 248, 248)
TEXT_COLOR = (70, 70, 70)
ACCENT_COLOR = (210, 210, 210)


def _read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Unable to read image: {path}")
    return image


def _resize_to_width(image: np.ndarray, width: int) -> np.ndarray:
    height, current_width = image.shape[:2]
    scale = width / current_width
    target_height = max(1, int(round(height * scale)))
    return cv2.resize(image, (width, target_height), interpolation=cv2.INTER_AREA)


def _make_input_preview(case_dir: Path) -> None:
    input_paths = sorted((case_dir / "inputs").glob("*.png"))
    if not input_paths:
        return

    resized = [_resize_to_width(_read_image(path), INPUT_WIDTH) for path in input_paths]
    max_height = max(image.shape[0] for image in resized)
    canvas_width = len(resized) * INPUT_WIDTH + (len(resized) + 1) * PADDING
    canvas_height = max_height + LABEL_HEIGHT + PADDING * 2
    canvas = np.full((canvas_height, canvas_width, 3), BG_COLOR, dtype=np.uint8)

    for idx, image in enumerate(resized, start=1):
        x = PADDING + (idx - 1) * (INPUT_WIDTH + PADDING)
        y = PADDING + LABEL_HEIGHT
        canvas[y : y + image.shape[0], x : x + image.shape[1]] = image
        cv2.putText(
            canvas,
            f"Input {idx}",
            (x, PADDING + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            TEXT_COLOR,
            2,
            cv2.LINE_AA,
        )
        cv2.rectangle(
            canvas,
            (x - 2, y - 2),
            (x + image.shape[1] + 1, y + image.shape[0] + 1),
            ACCENT_COLOR,
            1,
        )

    cv2.imwrite(str(case_dir / "preview-inputs.png"), canvas)


def _make_stitched_preview(case_dir: Path) -> None:
    stitched_path = case_dir / "stitched.png"
    if not stitched_path.exists():
        return

    stitched = _resize_to_width(_read_image(stitched_path), STITCHED_WIDTH)
    cv2.imwrite(str(case_dir / "preview-stitched.png"), stitched)


def main() -> int:
    for case_dir in sorted(CASES_DIR.iterdir()):
        if not case_dir.is_dir():
            continue
        _make_input_preview(case_dir)
        _make_stitched_preview(case_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
