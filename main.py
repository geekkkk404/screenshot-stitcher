"""CLI entrypoint for stitching vertically scrolling iPhone screenshots."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import cv2

from config import (
    BOTTOM_CROP,
    SAFE_AREA_BOTTOM,
    STATUSBAR_HEIGHT,
    TABBAR_HEIGHT,
    TEMPLATE_HEIGHT,
    THRESHOLD,
    TOP_CROP,
    X_MARGIN,
)
from stitcher import StitchParams, stitch_images


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Stitch vertically scrolling iPhone screenshots into one long image."
    )
    parser.add_argument("images", nargs="+", help="Input image paths (at least 2).")
    parser.add_argument("-o", "--output", default="output.png", help="Output image path.")
    parser.add_argument(
        "--top-crop",
        type=int,
        default=None,
        help=f"Top crop in pixels (default {TOP_CROP}; {STATUSBAR_HEIGHT} with --no-navbar).",
    )
    parser.add_argument(
        "--bottom-crop",
        type=int,
        default=None,
        help=f"Bottom crop in pixels (default {BOTTOM_CROP}; {SAFE_AREA_BOTTOM} with --no-tabbar).",
    )
    parser.add_argument(
        "--no-navbar",
        action="store_true",
        help=f"Use only the status bar height as top crop ({STATUSBAR_HEIGHT}px).",
    )
    tabbar_group = parser.add_mutually_exclusive_group()
    tabbar_group.add_argument(
        "--has-tabbar",
        dest="has_tabbar",
        action="store_true",
        default=True,
        help=f"Assume the page has a tab bar (default, bottom_crop={TABBAR_HEIGHT + SAFE_AREA_BOTTOM}).",
    )
    tabbar_group.add_argument(
        "--no-tabbar",
        dest="has_tabbar",
        action="store_false",
        help=f"Assume the page has no tab bar (bottom_crop={SAFE_AREA_BOTTOM}).",
    )
    parser.add_argument("--x-margin", type=int, default=X_MARGIN, help="Left/right edge crop in pixels.")
    parser.add_argument(
        "--template-height",
        type=int,
        default=TEMPLATE_HEIGHT,
        help="Template height in pixels used during overlap matching.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=THRESHOLD,
        help="Confidence threshold for accepting overlap matches.",
    )
    return parser.parse_args()


def load_images(paths: list[str]) -> list:
    """Load input images from disk."""
    images = []
    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            raise FileNotFoundError(f"Input file does not exist: {path}")

        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"Failed to read image: {path}")
        images.append(image)
    return images


def resolve_crop_values(args: argparse.Namespace) -> tuple[int, int]:
    """Resolve the final top/bottom crop values from flags and defaults."""
    top_crop = args.top_crop if args.top_crop is not None else (STATUSBAR_HEIGHT if args.no_navbar else TOP_CROP)
    bottom_crop = args.bottom_crop if args.bottom_crop is not None else (BOTTOM_CROP if args.has_tabbar else SAFE_AREA_BOTTOM)
    return top_crop, bottom_crop


def validate_args(args: argparse.Namespace, top_crop: int, bottom_crop: int) -> None:
    """Validate top-level CLI arguments."""
    if len(args.images) < 2:
        raise ValueError("At least 2 input images are required.")

    if top_crop < 0 or bottom_crop < 0 or args.x_margin < 0:
        raise ValueError("top-crop, bottom-crop, and x-margin must be non-negative integers.")

    if args.template_height <= 0:
        raise ValueError("template-height must be a positive integer.")

    if not (0.0 <= args.threshold <= 1.0):
        raise ValueError("threshold must be between 0 and 1.")


def main() -> int:
    """Run the CLI program."""
    args = parse_args()

    try:
        top_crop, bottom_crop = resolve_crop_values(args)
        validate_args(args, top_crop, bottom_crop)
        images = load_images(args.images)

        params = StitchParams(
            top_crop=top_crop,
            bottom_crop=bottom_crop,
            x_margin=args.x_margin,
            template_height=args.template_height,
            threshold=args.threshold,
        )

        stitched, infos = stitch_images(images, params)

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        ok = cv2.imwrite(str(output_path), stitched)
        if not ok:
            raise IOError(f"Failed to write output image: {output_path}")

        for idx, info in enumerate(infos, start=1):
            status = "overlap accepted" if info.overlapped else "fallback stitch"
            print(
                f"Pair {idx}: "
                f"confidence={info.confidence:.4f}, "
                f"consensus={info.consensus:.2f}, "
                f"offset={info.offset}px, "
                f"overlap={info.overlap_height}px, "
                f"mode={info.mode}, "
                f"{status}",
            )

        print(f"Done. Output written to: {output_path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
