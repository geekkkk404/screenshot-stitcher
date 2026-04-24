"""Core logic for vertically stitching screenshots."""

from __future__ import annotations

from dataclasses import dataclass, replace

import cv2
import numpy as np


@dataclass
class StitchParams:
    """Collection of stitching parameters."""

    top_crop: int
    bottom_crop: int
    x_margin: int
    template_height: int
    threshold: float
    search_ratio: float = 0.85
    consensus_tolerance: int = 60
    min_consensus: float = 0.2
    orb_match_target: int = 20
    orb_max_matches: int = 150


@dataclass
class PairStitchInfo:
    """Summary of one pairwise stitch result."""

    confidence: float
    overlapped: bool
    offset: int
    overlap_height: int
    seam: int
    consensus: float
    mode: str


@dataclass
class ProcessedImage:
    """Preprocessed image data used during matching."""

    content_gray: np.ndarray
    match_gray: np.ndarray
    match_edge: np.ndarray


@dataclass
class MatchCandidate:
    """One candidate vertical offset."""

    offset: int
    score: float
    source: str
    window_height: int


@dataclass
class OffsetEstimate:
    """Estimated vertical offset and supporting scores."""

    offset: int
    match_score: float
    consensus: float
    similarity: float
    feature_support: float
    local_anchor_support: float
    confidence: float
    overlap_height: int


@dataclass
class _PairStitchPlan:
    """Internal crop plan for one adjacent image pair."""

    info: PairStitchInfo
    prev_keep_end: int
    next_start: int


def _has_strong_match_evidence(estimate: OffsetEstimate, params: StitchParams) -> bool:
    """Allow strong global or local evidence to pass with a softer acceptance rule."""
    min_overlap = max(600, params.template_height * 3)
    return (
        estimate.match_score >= 0.50
        and estimate.similarity >= 0.38
        and estimate.overlap_height >= min_overlap
        and estimate.consensus >= 0.20
        and (
            estimate.feature_support >= 0.15
            or estimate.local_anchor_support >= 0.85
        )
    )


def _content_height(image: np.ndarray, params: StitchParams) -> int:
    """Return the usable content height after top/bottom cropping."""
    return image.shape[0] - params.top_crop - params.bottom_crop


def _validate_image_shape(image: np.ndarray, params: StitchParams, name: str) -> None:
    """Validate that a single image supports the requested crop and match settings."""
    height, width = image.shape[:2]
    content_height = _content_height(image, params)

    if height <= params.top_crop + params.bottom_crop:
        raise ValueError(
            f"{name} is too short; height must exceed top_crop + bottom_crop "
            f"({params.top_crop + params.bottom_crop})."
        )
    if width <= 2 * params.x_margin:
        raise ValueError(
            f"{name} is too narrow; width must exceed 2 * x_margin ({2 * params.x_margin})."
        )
    if params.template_height <= 0:
        raise ValueError("template_height must be a positive integer.")
    if content_height < params.template_height:
        raise ValueError(
            f"{name} does not have enough usable content height; "
            f"H - top_crop - bottom_crop must be >= template_height ({params.template_height})."
        )


def _validate_image_pair(img_prev: np.ndarray, img_next: np.ndarray) -> None:
    """Validate basic compatibility before stitching a pair of images."""
    if img_prev.shape[1] != img_next.shape[1]:
        raise ValueError(
            f"Image widths do not match: previous={img_prev.shape[1]}px, next={img_next.shape[1]}px."
        )


def _preprocess(image: np.ndarray, params: StitchParams) -> ProcessedImage:
    """Build grayscale and edge representations used for matching and seam selection."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    y_start = params.top_crop
    y_end = image.shape[0] - params.bottom_crop
    content_gray = gray[y_start:y_end, :]
    content_gray = cv2.GaussianBlur(content_gray, (3, 3), 0)

    x_start = params.x_margin
    x_end = image.shape[1] - params.x_margin
    match_gray = content_gray[:, x_start:x_end]

    sobel_y = cv2.Sobel(match_gray, cv2.CV_16S, dx=0, dy=1, ksize=3)
    match_edge = cv2.convertScaleAbs(sobel_y)

    return ProcessedImage(
        content_gray=content_gray,
        match_gray=match_gray,
        match_edge=match_edge,
    )


def _normalized_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Compute normalized correlation between two arrays of the same shape."""
    a_float = a.astype(np.float32)
    b_float = b.astype(np.float32)
    a_centered = a_float - float(np.mean(a_float))
    b_centered = b_float - float(np.mean(b_float))
    denom = float(np.linalg.norm(a_centered) * np.linalg.norm(b_centered))
    if denom == 0:
        return 0.0
    return float(np.clip(np.sum(a_centered * b_centered) / denom, -1.0, 1.0))


def _extract_overlap(
    prev_array: np.ndarray,
    next_array: np.ndarray,
    offset: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Extract the overlapping slices implied by a content-space vertical offset."""
    prev_height = prev_array.shape[0]
    next_height = next_array.shape[0]

    if offset >= 0:
        prev_start = offset
        next_start = 0
        overlap_height = min(prev_height - prev_start, next_height)
    else:
        prev_start = 0
        next_start = -offset
        overlap_height = min(prev_height, next_height - next_start)

    if overlap_height <= 0:
        empty_prev = prev_array[:0]
        empty_next = next_array[:0]
        return empty_prev, empty_next, 0

    prev_overlap = prev_array[prev_start : prev_start + overlap_height]
    next_overlap = next_array[next_start : next_start + overlap_height]
    return prev_overlap, next_overlap, int(overlap_height)


def _sample_overlap(a: np.ndarray, b: np.ndarray, max_height: int) -> tuple[np.ndarray, np.ndarray]:
    """Downsample an overlap region to a manageable height for similarity checks."""
    if a.shape[0] <= max_height:
        return a, b

    target_size = (a.shape[1], max_height)
    return (
        cv2.resize(a, target_size, interpolation=cv2.INTER_AREA),
        cv2.resize(b, target_size, interpolation=cv2.INTER_AREA),
    )


def _compute_similarity(
    prev: ProcessedImage,
    next_: ProcessedImage,
    offset: int,
    params: StitchParams,
) -> tuple[float, int]:
    """Score one offset by comparing grayscale and edge consistency in the overlap."""
    prev_edge_overlap, next_edge_overlap, overlap_height = _extract_overlap(
        prev.match_edge,
        next_.match_edge,
        offset,
    )
    if overlap_height <= 0:
        return 0.0, 0

    sample_height = max(params.template_height * 2, 320)
    prev_edge_sample, next_edge_sample = _sample_overlap(prev_edge_overlap, next_edge_overlap, sample_height)
    edge_corr = max(0.0, _normalized_correlation(prev_edge_sample, next_edge_sample))

    prev_gray_overlap, next_gray_overlap, _ = _extract_overlap(
        prev.match_gray,
        next_.match_gray,
        offset,
    )
    prev_gray_sample, next_gray_sample = _sample_overlap(prev_gray_overlap, next_gray_overlap, sample_height)
    gray_corr = max(0.0, _normalized_correlation(prev_gray_sample, next_gray_sample))
    gray_diff = float(np.mean(np.abs(prev_gray_sample.astype(np.float32) - next_gray_sample.astype(np.float32))))
    gray_score = float(np.clip(1.0 - gray_diff / 255.0, 0.0, 1.0))

    similarity = 0.45 * edge_corr + 0.30 * gray_corr + 0.25 * gray_score
    return float(similarity), overlap_height


def _build_template_heights(prev: ProcessedImage, next_: ProcessedImage, params: StitchParams) -> list[int]:
    """Generate a set of multi-scale template heights."""
    max_height = min(prev.match_gray.shape[0], int(next_.match_gray.shape[0] * params.search_ratio))
    raw_heights = {
        params.template_height,
        max(400, params.template_height * 2),
        max(600, params.template_height * 3),
        max(800, params.template_height * 4),
        max(1000, params.template_height * 5),
        1200,
        int(prev.match_gray.shape[0] * 0.35),
        int(prev.match_gray.shape[0] * 0.45),
    }

    heights = sorted(
        {
            int(height)
            for height in raw_heights
            if max(80, params.template_height) <= int(height) <= max_height - 20
        }
    )

    if not heights:
        height = min(max_height - 20, max(params.template_height, 80))
        return [height]
    return heights


def _match_template_offset(
    prev_array: np.ndarray,
    next_array: np.ndarray,
    template_height: int,
    search_end: int,
    source: str,
) -> MatchCandidate | None:
    """Generate one offset candidate with 2D template matching."""
    template = prev_array[-template_height:, :]
    search_area = next_array[:search_end, :]
    if search_area.shape[0] < template.shape[0]:
        return None

    match_map = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(match_map)
    offset = (prev_array.shape[0] - template_height) - max_loc[1]
    return MatchCandidate(
        offset=int(offset),
        score=float(max_val),
        source=source,
        window_height=template_height,
    )


def _match_profile_offset(
    prev_array: np.ndarray,
    next_array: np.ndarray,
    template_height: int,
    search_end: int,
) -> MatchCandidate | None:
    """Generate one offset candidate by matching 1D row profiles."""
    prev_profile = prev_array.mean(axis=1).astype(np.float32)
    next_profile = next_array.mean(axis=1).astype(np.float32)

    template = prev_profile[-template_height:]
    search = next_profile[:search_end]
    if search.shape[0] < template.shape[0]:
        return None

    match_map = cv2.matchTemplate(
        search.reshape(-1, 1),
        template.reshape(-1, 1),
        cv2.TM_CCOEFF_NORMED,
    )
    _, max_val, _, max_loc = cv2.minMaxLoc(match_map)
    offset = (prev_array.shape[0] - template_height) - max_loc[1]
    return MatchCandidate(
        offset=int(offset),
        score=float(max_val),
        source="profile",
        window_height=template_height,
    )


def _collect_candidates(prev: ProcessedImage, next_: ProcessedImage, params: StitchParams) -> list[MatchCandidate]:
    """Collect offset candidates from multi-scale 2D and 1D matching passes."""
    heights = _build_template_heights(prev, next_, params)
    search_end = min(next_.match_gray.shape[0], max(heights))
    search_end = max(search_end, int(next_.match_gray.shape[0] * params.search_ratio))

    candidates: list[MatchCandidate] = []
    for template_height in heights:
        for source, prev_array, next_array in (
            ("edge", prev.match_edge, next_.match_edge),
            ("gray", prev.match_gray, next_.match_gray),
        ):
            candidate = _match_template_offset(prev_array, next_array, template_height, search_end, source)
            if candidate is not None:
                candidates.append(candidate)

        profile_candidate = _match_profile_offset(prev.match_edge, next_.match_edge, template_height, search_end)
        if profile_candidate is not None:
            candidates.append(profile_candidate)

    return candidates


def _cluster_candidates(candidates: list[MatchCandidate], tolerance: int) -> list[list[MatchCandidate]]:
    """Cluster candidate offsets within a fixed tolerance."""
    if not candidates:
        return []

    sorted_candidates = sorted(candidates, key=lambda candidate: candidate.offset)
    clusters: list[list[MatchCandidate]] = [[sorted_candidates[0]]]
    for candidate in sorted_candidates[1:]:
        current_cluster = clusters[-1]
        cluster_center = int(round(sum(item.offset for item in current_cluster) / len(current_cluster)))
        if abs(candidate.offset - cluster_center) <= tolerance:
            current_cluster.append(candidate)
        else:
            clusters.append([candidate])
    return clusters


def _candidate_weight(candidate: MatchCandidate) -> float:
    """Compute the aggregation weight for one candidate."""
    return max(candidate.score, 0.01) * (1.0 + candidate.window_height / 1000.0)


def _window_positions(length: int, window: int, step: int) -> list[int]:
    """Return sliding window start positions, including the final aligned window."""
    if length <= window:
        return [0]

    positions = list(range(0, length - window + 1, step))
    last_start = length - window
    if positions[-1] != last_start:
        positions.append(last_start)
    return positions


def _compute_feature_support(
    prev: ProcessedImage,
    next_: ProcessedImage,
    offset: int,
    params: StitchParams,
) -> float:
    """Re-score an offset candidate with ORB feature consistency."""
    prev_overlap, next_overlap, overlap_height = _extract_overlap(prev.match_gray, next_.match_gray, offset)
    if overlap_height < max(200, params.template_height):
        return 0.0

    if overlap_height > 1200:
        start = (overlap_height - 1200) // 2
        prev_overlap = prev_overlap[start : start + 1200]
        next_overlap = next_overlap[start : start + 1200]

    orb = cv2.ORB_create(nfeatures=1200)
    kp_prev, des_prev = orb.detectAndCompute(prev_overlap, None)
    kp_next, des_next = orb.detectAndCompute(next_overlap, None)
    if des_prev is None or des_next is None:
        return 0.0

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = matcher.match(des_prev, des_next)
    matches = sorted(matches, key=lambda match: match.distance)[: params.orb_max_matches]

    good_matches = 0
    for match in matches:
        prev_point = kp_prev[match.queryIdx].pt
        next_point = kp_next[match.trainIdx].pt
        dx = prev_point[0] - next_point[0]
        dy = prev_point[1] - next_point[1]
        if abs(dx) < 20 and abs(dy) < 20:
            good_matches += 1

    return float(min(1.0, good_matches / max(params.orb_match_target, 1)))


def _compute_local_anchor_support(
    prev: ProcessedImage,
    next_: ProcessedImage,
    offset: int,
    params: StitchParams,
) -> float:
    """Score sparse but distinctive local anchors inside the overlap."""
    prev_gray_overlap, next_gray_overlap, overlap_height = _extract_overlap(
        prev.match_gray,
        next_.match_gray,
        offset,
    )
    if overlap_height < max(200, params.template_height):
        return 0.0

    prev_edge_overlap, next_edge_overlap, _ = _extract_overlap(
        prev.match_edge,
        next_.match_edge,
        offset,
    )

    window_height = min(max(params.template_height, 120), overlap_height)
    window_width = min(max(prev_gray_overlap.shape[1] // 4, 120), 220)
    if window_height < 80 or window_width < 60:
        return 0.0

    step_y = max(24, window_height // 3)
    step_x = max(24, window_width // 3)

    window_scores: list[float] = []
    for y in _window_positions(overlap_height, window_height, step_y):
        for x in _window_positions(prev_gray_overlap.shape[1], window_width, step_x):
            prev_gray_window = prev_gray_overlap[y : y + window_height, x : x + window_width]
            next_gray_window = next_gray_overlap[y : y + window_height, x : x + window_width]
            prev_edge_window = prev_edge_overlap[y : y + window_height, x : x + window_width]
            next_edge_window = next_edge_overlap[y : y + window_height, x : x + window_width]

            gray_std = min(float(np.std(prev_gray_window)), float(np.std(next_gray_window)))
            edge_mean = min(float(np.mean(prev_edge_window)), float(np.mean(next_edge_window)))
            if gray_std < 10.0 and edge_mean < 8.0:
                continue

            gray_corr = max(0.0, _normalized_correlation(prev_gray_window, next_gray_window))
            edge_corr = max(0.0, _normalized_correlation(prev_edge_window, next_edge_window))
            gray_diff = float(
                np.mean(
                    np.abs(
                        prev_gray_window.astype(np.float32) - next_gray_window.astype(np.float32)
                    )
                )
            )
            gray_score = float(np.clip(1.0 - gray_diff / 255.0, 0.0, 1.0))

            window_score = 0.40 * gray_corr + 0.35 * edge_corr + 0.25 * gray_score
            window_scores.append(float(window_score))

    if not window_scores:
        return 0.0

    window_scores.sort(reverse=True)
    top_scores = window_scores[: min(3, len(window_scores))]
    strong_fraction = sum(score >= 0.80 for score in window_scores) / len(window_scores)
    support = (
        0.55 * top_scores[0]
        + 0.35 * float(sum(top_scores) / len(top_scores))
        + 0.10 * strong_fraction
    )
    return float(np.clip(support, 0.0, 1.0))


def _estimate_offset(prev: ProcessedImage, next_: ProcessedImage, params: StitchParams) -> OffsetEstimate:
    """Estimate the best vertical offset from templates, profiles, and ORB verification."""
    candidates = _collect_candidates(prev, next_, params)
    if not candidates:
        raise ValueError("No overlap candidates were generated.")

    clusters = _cluster_candidates(candidates, params.consensus_tolerance)
    best_estimate: OffsetEstimate | None = None

    for cluster in clusters:
        total_weight = sum(_candidate_weight(candidate) for candidate in cluster)
        offset = int(round(sum(candidate.offset * _candidate_weight(candidate) for candidate in cluster) / total_weight))
        match_score = float(sum(candidate.score for candidate in cluster) / len(cluster))
        consensus = len(cluster) / len(candidates)
        similarity, overlap_height = _compute_similarity(prev, next_, offset, params)
        feature_support = _compute_feature_support(prev, next_, offset, params)
        local_anchor_support = _compute_local_anchor_support(prev, next_, offset, params)

        confidence = float(
            np.clip(
                0.30 * match_score
                + 0.20 * similarity
                + 0.15 * consensus
                + 0.20 * feature_support
                + 0.15 * local_anchor_support,
                0.0,
                1.0,
            )
        )

        if overlap_height < max(80, params.template_height):
            confidence *= 0.7

        estimate = OffsetEstimate(
            offset=offset,
            match_score=match_score,
            consensus=consensus,
            similarity=similarity,
            feature_support=feature_support,
            local_anchor_support=local_anchor_support,
            confidence=confidence,
            overlap_height=overlap_height,
        )

        if best_estimate is None:
            best_estimate = estimate
            continue

        best_key = (
            best_estimate.confidence,
            best_estimate.local_anchor_support,
            best_estimate.feature_support,
            best_estimate.similarity,
            best_estimate.match_score,
        )
        estimate_key = (
            estimate.confidence,
            estimate.local_anchor_support,
            estimate.feature_support,
            estimate.similarity,
            estimate.match_score,
        )
        if estimate_key > best_key:
            best_estimate = estimate

    if best_estimate is None:
        raise ValueError("No usable offset estimate was found.")
    return best_estimate


def _detect_stable_overlap_start(row_cost: np.ndarray, overlap_height: int) -> int:
    """Find a stable overlap start to avoid dynamic headers and collapsing chrome."""
    if overlap_height <= 0:
        return 0
    if overlap_height < 240:
        return min(24, overlap_height // 6)

    # For larger overlaps, keep the seam away from the dynamic top region.
    guard = min(max(48, overlap_height // 5), max(48, overlap_height - 120))
    stable_window = min(max(80, overlap_height // 8), max(80, overlap_height // 3))
    stable_window = min(stable_window, max(1, overlap_height - guard))
    if stable_window <= 1:
        return guard

    stable_kernel = np.ones(stable_window, dtype=np.float32) / stable_window
    rolling_mean = np.convolve(row_cost, stable_kernel, mode="same")

    candidate_end = max(guard + 1, overlap_height - stable_window // 2)
    candidate_slice = rolling_mean[guard:candidate_end]
    if candidate_slice.size == 0:
        return guard

    baseline = float(np.percentile(candidate_slice, 30))
    mean_threshold = max(6.0, baseline * 1.35)
    max_threshold = max(10.0, mean_threshold * 1.45)

    for start in range(guard, candidate_end):
        end = min(overlap_height, start + stable_window)
        segment = row_cost[start:end]
        if segment.size < max(40, stable_window // 2):
            break
        if float(np.mean(segment)) <= mean_threshold and float(np.max(segment)) <= max_threshold:
            return start

    return guard


def _select_seam(
    prev: ProcessedImage,
    next_: ProcessedImage,
    offset: int,
    min_seam: int | None = None,
    max_seam: int | None = None,
) -> int:
    """Choose a horizontal seam inside the overlap, optionally within content-space bounds."""
    prev_overlap, next_overlap, overlap_height = _extract_overlap(
        prev.match_gray,
        next_.match_gray,
        offset,
    )
    if overlap_height <= 0:
        return max(offset, 0)

    diff = np.abs(prev_overlap.astype(np.float32) - next_overlap.astype(np.float32))
    row_cost = np.mean(diff, axis=1)

    window = min(21, overlap_height if overlap_height % 2 == 1 else overlap_height - 1)
    if window >= 3:
        kernel = np.ones(window, dtype=np.float32) / window
        row_cost = np.convolve(row_cost, kernel, mode="same")

    margin = min(24, overlap_height // 6)
    local_lower = 0
    local_upper = overlap_height - 1
    if min_seam is not None:
        local_lower = max(local_lower, int(min_seam) - offset)
    if max_seam is not None:
        local_upper = min(local_upper, int(max_seam) - offset)
    local_lower = max(0, min(overlap_height - 1, local_lower))
    local_upper = max(0, min(overlap_height - 1, local_upper))
    if local_lower > local_upper:
        local_lower, local_upper = local_upper, local_lower

    start = max(margin, _detect_stable_overlap_start(row_cost, overlap_height), local_lower)
    end = min(overlap_height - margin, local_upper + 1)

    if start >= end:
        seam_local = (start + end - 1) // 2
        seam_local = int(min(max(seam_local, local_lower), local_upper))
    else:
        seam_local = int(np.argmin(row_cost[start:end]) + start)

    return int(offset + seam_local)


def _clamp_int(value: int, lower: int, upper: int) -> int:
    """Clamp an integer value to an inclusive range."""
    return int(min(max(value, lower), upper))


def _crop_bounds_from_content_cuts(
    img_prev: np.ndarray,
    img_next: np.ndarray,
    params: StitchParams,
    prev_content_cut: int,
    next_content_cut: int,
) -> tuple[int, int]:
    """Convert content-space cuts to absolute image row bounds."""
    prev_keep_end = _clamp_int(params.top_crop + prev_content_cut, 0, img_prev.shape[0])
    next_start = _clamp_int(params.top_crop + next_content_cut, 0, img_next.shape[0])
    return prev_keep_end, next_start


def _build_pair_stitch_plan(
    img_prev: np.ndarray,
    img_next: np.ndarray,
    params: StitchParams,
) -> _PairStitchPlan:
    """Estimate one adjacent pair and return the pairwise crop plan."""
    _validate_image_shape(img_prev, params, "Previous image")
    _validate_image_shape(img_next, params, "Next image")
    _validate_image_pair(img_prev, img_next)

    prev_processed = _preprocess(img_prev, params)
    next_processed = _preprocess(img_next, params)
    prev_content_height = prev_processed.content_gray.shape[0]

    estimate = _estimate_offset(prev_processed, next_processed, params)
    overlap_found = (
        estimate.offset >= 0
        and estimate.offset < prev_content_height
        and estimate.overlap_height > 0
        and estimate.consensus >= params.min_consensus
        and (
            estimate.confidence >= params.threshold
            or _has_strong_match_evidence(estimate, params)
        )
    )

    if overlap_found:
        seam = _select_seam(prev_processed, next_processed, estimate.offset)
        prev_content_cut = seam
        next_content_cut = max(0, seam - estimate.offset)
        overlapped = True
        mode = "matched"
    else:
        seam = prev_content_height
        prev_content_cut = prev_content_height
        next_content_cut = 0
        overlapped = False
        mode = "fallback"

    prev_keep_end, next_start = _crop_bounds_from_content_cuts(
        img_prev,
        img_next,
        params,
        prev_content_cut,
        next_content_cut,
    )

    return _PairStitchPlan(
        info=PairStitchInfo(
            confidence=estimate.confidence,
            overlapped=overlapped,
            offset=estimate.offset,
            overlap_height=estimate.overlap_height,
            seam=seam,
            consensus=estimate.consensus,
            mode=mode,
        ),
        prev_keep_end=prev_keep_end,
        next_start=next_start,
    )


def stitch_pair(
    img_prev: np.ndarray,
    img_next: np.ndarray,
    params: StitchParams,
) -> tuple[np.ndarray, PairStitchInfo]:
    """Stitch a pair of images and return both the output and match metadata."""
    plan = _build_pair_stitch_plan(img_prev, img_next, params)

    prev_part = img_prev[:plan.prev_keep_end, :]
    next_part = img_next[plan.next_start:, :]
    if prev_part.size == 0 or next_part.size == 0:
        raise ValueError("One stitch segment is empty; the crop settings may be too aggressive.")

    stitched = np.vstack([prev_part, next_part])
    return stitched, plan.info


def _content_starts_from_pair_plans(
    images: list[np.ndarray],
    plans: list[_PairStitchPlan],
    params: StitchParams,
) -> list[int]:
    """Estimate each original image's top content row in global scroll coordinates."""
    content_starts = [0]
    for idx, plan in enumerate(plans):
        if plan.info.overlapped:
            delta = max(0, plan.info.offset)
        else:
            delta = _content_height(images[idx], params)
        content_starts.append(content_starts[-1] + delta)
    return content_starts


def _boundary_gap(params: StitchParams) -> int:
    """Minimum preferred contribution from an intermediate image."""
    return max(1, min(48, params.template_height // 4))


def _boundary_interval(
    index: int,
    plan: _PairStitchPlan,
    content_starts: list[int],
    content_heights: list[int],
) -> tuple[int, int]:
    """Return the legal global boundary interval for one pair."""
    if plan.info.overlapped:
        overlap_start = content_starts[index] + max(0, plan.info.offset)
        overlap_end = overlap_start + plan.info.overlap_height - 1
        prev_end = content_starts[index] + content_heights[index] - 1
        next_end = content_starts[index + 1] + content_heights[index + 1] - 1
        lower = max(content_starts[index], content_starts[index + 1], overlap_start)
        upper = min(prev_end, next_end, overlap_end)
        if lower <= upper:
            return int(lower), int(upper)

    boundary = content_starts[index] + content_heights[index]
    return int(boundary), int(boundary)


def _preferred_boundaries(
    plans: list[_PairStitchPlan],
    content_starts: list[int],
    content_heights: list[int],
) -> list[int]:
    """Map pairwise seam choices into global content coordinates."""
    preferred: list[int] = []
    for idx, plan in enumerate(plans):
        if plan.info.overlapped:
            preferred.append(content_starts[idx] + plan.info.seam)
        else:
            preferred.append(content_starts[idx] + content_heights[idx])
    return preferred


def _latest_feasible_boundaries(
    intervals: list[tuple[int, int]],
    gap: int,
) -> list[int] | None:
    """Return latest legal boundary values that still allow a monotonic sequence."""
    latest = [0] * len(intervals)
    latest[-1] = intervals[-1][1]
    if latest[-1] < intervals[-1][0]:
        return None

    for idx in range(len(intervals) - 2, -1, -1):
        latest[idx] = min(intervals[idx][1], latest[idx + 1] - gap)
        if latest[idx] < intervals[idx][0]:
            return None
    return latest


def _solve_boundary_positions(
    processed_images: list[ProcessedImage],
    plans: list[_PairStitchPlan],
    content_starts: list[int],
    intervals: list[tuple[int, int]],
    preferred: list[int],
    params: StitchParams,
) -> list[int]:
    """Choose monotonic global boundaries, reselecting seams inside constrained ranges."""
    for gap in (_boundary_gap(params), 1, 0):
        latest = _latest_feasible_boundaries(intervals, gap)
        if latest is None:
            continue

        positions: list[int] = []
        previous: int | None = None
        feasible = True

        for idx, plan in enumerate(plans):
            lower = intervals[idx][0]
            if previous is not None:
                lower = max(lower, previous + gap)
            upper = latest[idx]
            if lower > upper:
                feasible = False
                break

            if plan.info.overlapped:
                min_seam = lower - content_starts[idx]
                max_seam = upper - content_starts[idx]
                seam = _select_seam(
                    processed_images[idx],
                    processed_images[idx + 1],
                    plan.info.offset,
                    min_seam=min_seam,
                    max_seam=max_seam,
                )
                boundary = content_starts[idx] + seam
            else:
                boundary = preferred[idx]

            boundary = _clamp_int(boundary, lower, upper)
            positions.append(boundary)
            previous = boundary

        if feasible:
            return positions

    return [
        _clamp_int(boundary, lower, upper)
        for boundary, (lower, upper) in zip(preferred, intervals, strict=True)
    ]


def _coordinate_pair_plans(
    images: list[np.ndarray],
    plans: list[_PairStitchPlan],
    params: StitchParams,
) -> list[_PairStitchPlan]:
    """Coordinate adjacent pair seams before assembling multiple original images."""
    if len(plans) <= 1:
        return plans

    content_heights = [_content_height(image, params) for image in images]
    content_starts = _content_starts_from_pair_plans(images, plans, params)
    intervals = [
        _boundary_interval(idx, plan, content_starts, content_heights)
        for idx, plan in enumerate(plans)
    ]
    preferred = _preferred_boundaries(plans, content_starts, content_heights)
    processed_images = [_preprocess(image, params) for image in images]
    boundaries = _solve_boundary_positions(
        processed_images,
        plans,
        content_starts,
        intervals,
        preferred,
        params,
    )

    coordinated: list[_PairStitchPlan] = []
    for idx, (plan, boundary) in enumerate(zip(plans, boundaries, strict=True)):
        prev_content_cut = boundary - content_starts[idx]
        next_content_cut = boundary - content_starts[idx + 1]
        prev_keep_end, next_start = _crop_bounds_from_content_cuts(
            images[idx],
            images[idx + 1],
            params,
            prev_content_cut,
            next_content_cut,
        )

        mode = plan.info.mode
        if plan.info.overlapped and prev_content_cut != plan.info.seam:
            mode = f"{plan.info.mode}-coordinated"

        coordinated.append(
            _PairStitchPlan(
                info=replace(plan.info, seam=prev_content_cut, mode=mode),
                prev_keep_end=prev_keep_end,
                next_start=next_start,
            )
        )

    return coordinated


def _assemble_from_pair_plans(
    images: list[np.ndarray],
    plans: list[_PairStitchPlan],
) -> np.ndarray:
    """Assemble final output from coordinated original-image crop plans."""
    parts: list[np.ndarray] = []
    last_index = len(images) - 1

    for idx, image in enumerate(images):
        start = 0 if idx == 0 else plans[idx - 1].next_start
        end = image.shape[0] if idx == last_index else plans[idx].prev_keep_end
        start = _clamp_int(start, 0, image.shape[0])
        end = _clamp_int(end, 0, image.shape[0])
        if end <= start:
            raise ValueError(
                f"Image {idx + 1} has no remaining contribution after seam coordination."
            )
        parts.append(image[start:end, :])

    return np.vstack(parts)


def stitch_images(images: list[np.ndarray], params: StitchParams) -> tuple[np.ndarray, list[PairStitchInfo]]:
    """Stitch multiple original images after coordinating adjacent pair seams."""
    if len(images) < 2:
        raise ValueError("At least 2 images are required for stitching.")

    plans = [
        _build_pair_stitch_plan(images[idx], images[idx + 1], params)
        for idx in range(len(images) - 1)
    ]
    plans = _coordinate_pair_plans(images, plans, params)
    stitched = _assemble_from_pair_plans(images, plans)
    return stitched, [plan.info for plan in plans]
