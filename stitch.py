#!/usr/bin/env python3
"""
截图拼接工具 - 自动检测顺序、重叠区域，无缝拼接多张截图。

用法：
    python stitch.py
    python stitch.py --input /path/to/input --output /path/to/output --done /path/to/done
"""

from __future__ import annotations

import argparse
import shutil
import sys
from itertools import permutations
from pathlib import Path

import cv2
import numpy as np


# ==================== 配置 ====================

DEFAULT_INPUT_DIR = Path(__file__).parent / "input"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output"
DEFAULT_DONE_DIR = Path(__file__).parent / "done"

# 图片文件扩展名
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}

# 重叠检测参数
OVERLAP_SEARCH_RANGE = 500  # 搜索重叠的最大范围（像素）
CORRELATION_WINDOW = 300    # 相关性计算窗口大小
SEAM_SEARCH_RANGE = 30      # 切割线搜索范围


# ==================== 核心算法 ====================

def load_images_from_dir(directory: Path) -> list[tuple[Path, np.ndarray]]:
    """从目录加载所有图片，返回 (路径, 图像) 列表。"""
    images = []
    for file in sorted(directory.iterdir()):
        if file.suffix.lower() in IMAGE_EXTENSIONS:
            img = cv2.imread(str(file))
            if img is not None:
                images.append((file, img))
    return images


def compute_correlation(gray1: np.ndarray, gray2: np.ndarray, offset: int) -> float:
    """计算两张灰度图在给定偏移量下的相关性。"""
    overlap_h = min(CORRELATION_WINDOW, gray1.shape[0], gray2.shape[0] - offset)
    if overlap_h <= 0:
        return 0.0

    region1 = gray1[-overlap_h:, :].astype(np.float32)
    region2 = gray2[offset:offset + overlap_h, :].astype(np.float32)

    # 归一化
    region1 = (region1 - np.mean(region1)) / (np.std(region1) + 1e-6)
    region2 = (region2 - np.mean(region2)) / (np.std(region2) + 1e-6)

    return float(np.mean(region1 * region2))


def find_best_offset(gray_top: np.ndarray, gray_bottom: np.ndarray) -> tuple[int, float]:
    """找到两张图之间的最佳重叠偏移量。返回 (偏移量, 相关性得分)。"""
    best_offset = 0
    best_score = -1.0

    for offset in range(0, min(OVERLAP_SEARCH_RANGE, gray_bottom.shape[0]), 5):
        score = compute_correlation(gray_top, gray_bottom, offset)
        if score > best_score:
            best_score = score
            best_offset = offset

    # 精细搜索
    for offset in range(max(0, best_offset - 10), best_offset + 10):
        score = compute_correlation(gray_top, gray_bottom, offset)
        if score > best_score:
            best_score = score
            best_offset = offset

    return best_offset, best_score


def find_clean_seam(gray_top: np.ndarray, gray_bottom: np.ndarray, offset: int) -> int:
    """在重叠区域找到最干净的切割线（白色背景行）。"""
    best_y = offset
    best_score = float("inf")

    for y in range(max(0, offset - SEAM_SEARCH_RANGE), offset + SEAM_SEARCH_RANGE):
        # 从顶部图取行
        top_row_idx = gray_top.shape[0] - (offset - y) - 1
        if top_row_idx < 0 or top_row_idx >= gray_top.shape[0]:
            continue

        # 从底部图取行
        bottom_row_idx = y
        if bottom_row_idx < 0 or bottom_row_idx >= gray_bottom.shape[0]:
            continue

        brightness_top = float(np.mean(gray_top[top_row_idx]))
        brightness_bottom = float(np.mean(gray_bottom[bottom_row_idx]))
        diff = abs(brightness_top - brightness_bottom)

        # 评分：差异小 + 亮度高（白色背景）= 好的切割线
        score = diff - brightness_top / 5

        if score < best_score:
            best_score = score
            best_y = y

    return best_y


def determine_order(images: list[tuple[Path, np.ndarray]]) -> list[tuple[Path, np.ndarray]]:
    """
    通过尝试所有排列，找到最佳拼接顺序。
    对每种排列计算相邻图片的重叠相关性，得分最高的为正确顺序。
    """
    if len(images) <= 1:
        return images

    n = len(images)
    gray_images = [cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) for _, img in images]

    best_order = None
    best_total_score = -1.0

    # 对于图片数量较多时，使用 pairwise 方法减少计算量
    if n <= 6:
        # 穷举所有排列
        for perm in permutations(range(n)):
            total_score = 0.0
            valid = True

            for i in range(n - 1):
                idx_top = perm[i]
                idx_bottom = perm[i + 1]

                offset, score = find_best_offset(gray_images[idx_top], gray_images[idx_bottom])

                # 检查偏移量是否合理（应该在 100-600 之间）
                if offset < 50 or offset > 700:
                    valid = False
                    break

                total_score += score

            if valid and total_score > best_total_score:
                best_total_score = total_score
                best_order = perm
    else:
        # 图片太多时，使用贪心算法
        best_order = _greedy_order(images, gray_images)

    if best_order is None:
        print("警告：无法确定最佳顺序，使用原始顺序")
        return images

    return [images[i] for i in best_order]


def _greedy_order(
    images: list[tuple[Path, np.ndarray]],
    gray_images: list[np.ndarray],
) -> tuple[int, ...]:
    """贪心算法确定顺序：从最可能在顶部的图片开始。"""
    n = len(images)
    used = set()
    order = []

    # 找最可能在顶部的图片（与其他图片的正向相关性总和最高）
    scores = []
    for i in range(n):
        total_score = 0.0
        for j in range(n):
            if i == j:
                continue
            offset, score = find_best_offset(gray_images[i], gray_images[j])
            if 50 < offset < 700:
                total_score += score
        scores.append((total_score, i))

    scores.sort(reverse=True)
    order.append(scores[0][1])
    used.add(scores[0][1])

    # 依次添加后续图片
    while len(order) < n:
        last = order[-1]
        best_next = -1
        best_score = -1.0

        for j in range(n):
            if j in used:
                continue
            offset, score = find_best_offset(gray_images[last], gray_images[j])
            if 50 < offset < 700 and score > best_score:
                best_score = score
                best_next = j

        if best_next == -1:
            # 找不到合适的下一张，添加剩余的
            for j in range(n):
                if j not in used:
                    order.append(j)
                    used.add(j)
                    break
        else:
            order.append(best_next)
            used.add(best_next)

    return tuple(order)


def stitch_pair(
    img_top: np.ndarray,
    img_bottom: np.ndarray,
) -> tuple[np.ndarray, dict]:
    """拼接两张图片，返回拼接结果和元信息。"""
    gray_top = cv2.cvtColor(img_top, cv2.COLOR_BGR2GRAY)
    gray_bottom = cv2.cvtColor(img_bottom, cv2.COLOR_BGR2GRAY)

    # 找最佳偏移量
    offset, score = find_best_offset(gray_top, gray_bottom)

    # 找干净的切割线
    seam_y = find_clean_seam(gray_top, gray_bottom, offset)

    # 执行切割
    cut_top = img_top.shape[0] - (offset - seam_y)
    cut_bottom = seam_y

    top_part = img_top[:cut_top, :]
    bottom_part = img_bottom[cut_bottom:, :]

    # 拼接
    stitched = np.vstack([top_part, bottom_part])

    info = {
        "offset": offset,
        "correlation": score,
        "seam_y": seam_y,
        "cut_top": cut_top,
        "cut_bottom": cut_bottom,
    }

    return stitched, info


def stitch_images(
    images: list[tuple[Path, np.ndarray]],
) -> tuple[np.ndarray, list[dict]]:
    """按正确顺序拼接多张图片。"""
    if len(images) == 0:
        raise ValueError("没有找到图片")
    if len(images) == 1:
        return images[0][1], []

    # 确定正确顺序
    ordered = determine_order(images)
    print(f"图片顺序: {[p.name for p, _ in ordered]}")

    # 依次拼接
    result = ordered[0][1]
    all_info = []

    for i in range(1, len(ordered)):
        print(f"拼接第 {i + 1} 张: {ordered[i][0].name}")
        result, info = stitch_pair(result, ordered[i][1])
        all_info.append(info)
        print(f"  偏移量={info['offset']}px, 相关性={info['correlation']:.4f}")

    return result, all_info


# ==================== 文件管理 ====================

def move_to_done(file_path: Path, done_dir: Path) -> Path:
    """将文件移动到 done 目录，保留原始文件名。"""
    dest = done_dir / file_path.name
    # 如果目标已存在，添加序号
    counter = 1
    while dest.exists():
        stem = file_path.stem
        suffix = file_path.suffix
        dest = done_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    shutil.move(str(file_path), str(dest))
    return dest


# ==================== 主函数 ====================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="截图拼接工具 - 自动检测顺序、重叠区域，无缝拼接多张截图"
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"输入图片目录 (默认: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"输出目录 (默认: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--done", "-d",
        type=Path,
        default=DEFAULT_DONE_DIR,
        help=f"已处理图片目录 (默认: {DEFAULT_DONE_DIR})",
    )
    parser.add_argument(
        "--name", "-n",
        type=str,
        default=None,
        help="输出文件名 (不含扩展名，默认: stitched_时间戳)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 确保目录存在
    args.input.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    args.done.mkdir(parents=True, exist_ok=True)

    # 加载图片
    print(f"扫描输入目录: {args.input}")
    images = load_images_from_dir(args.input)

    if len(images) == 0:
        print("输入目录中没有找到图片文件")
        return 0

    if len(images) == 1:
        print("只有一张图片，无需拼接，直接复制到输出目录")
        file_path, img = images[0]
        out_name = args.name or file_path.stem
        out_path = args.output / f"{out_name}{file_path.suffix}"
        cv2.imwrite(str(out_path), img)
        move_to_done(file_path, args.done)
        print(f"输出: {out_path}")
        return 0

    print(f"找到 {len(images)} 张图片: {[p.name for p, _ in images]}")

    # 拼接
    print("\n开始拼接...")
    result, info_list = stitch_images(images)

    # 保存结果
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = args.name or f"stitched_{timestamp}"
    out_path = args.output / f"{out_name}.png"
    cv2.imwrite(str(out_path), result)
    print(f"\n拼接完成: {out_path}")
    print(f"输出尺寸: {result.shape[1]}x{result.shape[0]}")

    # 移动源文件到 done
    print("\n移动源文件到 done 目录...")
    for file_path, _ in images:
        dest = move_to_done(file_path, args.done)
        print(f"  {file_path.name} -> {dest.name}")

    print("\n完成！")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
