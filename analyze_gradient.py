#!/usr/bin/env python3
"""Measure horizontal color bands in a gradient screenshot."""

import argparse
import json
import math
from pathlib import Path

from PIL import Image


def row_profile(image, excluded):
    image = image.convert("RGB")
    width, height = image.size
    pixels = image.load()
    x0, y0, x1, y1 = excluded or (width, height, width, height)
    profile = []
    for y in range(height):
        ranges = [(0, x0), (x1, width)] if y0 <= y < y1 else [(0, width)]
        sums = [0, 0, 0]
        count = 0
        for left, right in ranges:
            for x in range(max(0, left), min(width, right)):
                pixel = pixels[x, y]
                sums[0] += pixel[0]
                sums[1] += pixel[1]
                sums[2] += pixel[2]
                count += 1
        profile.append(tuple(round(value / count) for value in sums))
    return profile


def smooth(profile, radius=2):
    return [
        tuple(round(sum(profile[j][c] for j in range(max(0, i-radius), min(len(profile), i+radius+1))) /
                     (min(len(profile), i+radius+1) - max(0, i-radius))) for c in range(3))
        for i in range(len(profile))
    ]


def color_distance(a, b):
    return math.sqrt(sum((x-y) ** 2 for x, y in zip(a, b)))


def hex_color(color):
    return "#" + "".join(f"{round(value):02X}" for value in color)


def find_transitions(profile, threshold, min_gap):
    values = smooth(profile)
    deltas = [0] + [color_distance(values[i], values[i-1]) for i in range(1, len(values))]
    peaks = [
        (deltas[i], i) for i in range(1, len(deltas)-1)
        if deltas[i] >= threshold and deltas[i] >= deltas[i-1] and deltas[i] > deltas[i+1]
    ]
    selected = []
    for delta, row in sorted(peaks, reverse=True):
        if all(abs(row - old_row) >= min_gap for _, old_row in selected):
            selected.append((delta, row))
    return [
        {"row": row, "position": round(row / max(1, len(profile)-1), 4),
         "delta_rgb": round(delta, 1), "from": hex_color(values[row-1]), "to": hex_color(values[row])}
        for delta, row in sorted(selected, key=lambda item: item[1])
    ]


def fit_colors(samples, count):
    centers = [samples[0]]
    while len(centers) < count:
        centers.append(max(samples, key=lambda color: min(color_distance(color, center) for center in centers)))
    assignments = [0] * len(samples)
    for _ in range(18):
        sums = [[0, 0, 0, 0] for _ in centers]
        for index, color in enumerate(samples):
            group = min(range(count), key=lambda k: color_distance(color, centers[k]))
            assignments[index] = group
            for channel in range(3):
                sums[group][channel] += color[channel]
            sums[group][3] += 1
        centers = [tuple(total / row[3] for total in row[:3]) if row[3] else centers[k]
                   for k, row in enumerate(sums)]
    sse = sum(color_distance(color, centers[group]) ** 2 for color, group in zip(samples, assignments))
    return centers, assignments, sse


def estimate_palette(profile, max_colors):
    # Block averaging reduces the number of nearly identical neighboring scanlines.
    block = max(1, round(len(profile) / 80))
    samples = [
        tuple(sum(row[channel] for row in profile[start:start+block]) / len(profile[start:start+block])
              for channel in range(3))
        for start in range(0, len(profile), block)
    ]
    candidates = []
    for count in range(1, min(max_colors, len(samples)) + 1):
        centers, assignments, sse = fit_colors(samples, count)
        variance = max(sse / max(1, len(samples) * 3), 1)
        bic = len(samples) * math.log(variance) + (count * 4 - 1) * math.log(len(samples))
        candidates.append((bic, centers, assignments, count))
    _, centers, assignments, count = min(candidates, key=lambda item: item[0])
    result = []
    for group, color in enumerate(centers):
        weight = assignments.count(group) / len(assignments)
        if weight >= 0.015:
            result.append({"hex": hex_color(color), "share": round(weight, 3)})
    return {"estimated_core_colors": len(result), "sample_block_rows": block, "colors": result,
            "model_color_count": count, "bic": {str(k): round(value, 1) for value, _, _, k in candidates}}


def compare_profiles(before, after):
    if len(before) != len(after):
        return None
    row_deltas = [color_distance(a, b) for a, b in zip(before, after)]
    max_shift = min(64, len(before) // 4)
    shifts = []
    for shift in range(-max_shift, max_shift + 1):
        start, end = max(0, -shift), min(len(before), len(before) - shift)
        error = sum(color_distance(before[row], after[row + shift]) for row in range(start, end)) / (end - start)
        shifts.append((error, shift))
    aligned_distance, best_shift = min(shifts)
    return {"mean_rgb_distance": round(sum(row_deltas) / len(row_deltas), 2),
            "rows_over_10_rgb": sum(delta > 10 for delta in row_deltas),
            "max_rgb_distance": round(max(row_deltas), 1),
            "best_vertical_shift_rows": best_shift,
            "aligned_mean_rgb_distance": round(aligned_distance, 2)}


def parse_rect(value):
    try:
        rect = tuple(int(part) for part in value.split(","))
        if len(rect) != 4 or rect[2] <= rect[0] or rect[3] <= rect[1]:
            raise ValueError
        return rect
    except ValueError as error:
        raise argparse.ArgumentTypeError("use x0,y0,x1,y1") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--exclude", type=parse_rect, help="mask central input image: x0,y0,x1,y1")
    parser.add_argument("--change-threshold", type=float, default=18, help="minimum RGB jump for a band boundary")
    parser.add_argument("--min-gap", type=int, default=8, help="minimum rows between reported boundaries")
    parser.add_argument("--max-colors", type=int, default=10)
    parser.add_argument("--output", type=Path, help="write JSON report to this path")
    args = parser.parse_args()

    reports, profiles = [], []
    for path in args.images:
        with Image.open(path) as image:
            size = image.size
            profile = row_profile(image, args.exclude)
        profiles.append(profile)
        reports.append({
            "image": str(path), "size": list(size), "excluded_input_rect": args.exclude,
            "profile_rows": len(profile), "transitions": find_transitions(profile, args.change_threshold, args.min_gap),
            "palette": estimate_palette(profile, args.max_colors),
        })
    for index in range(1, len(reports)):
        reports[index]["change_from_previous_frame"] = compare_profiles(profiles[index-1], profiles[index])
    aggregate = None
    if profiles and all(len(profile) == len(profiles[0]) for profile in profiles):
        mean_profile = [
            tuple(round(sum(profile[row][channel] for profile in profiles) / len(profiles)) for channel in range(3))
            for row in range(len(profiles[0]))
        ]
        aggregate = {"frames_averaged": len(profiles), "profile_rows": len(mean_profile),
                    "transitions": find_transitions(mean_profile, args.change_threshold, args.min_gap),
                    "palette": estimate_palette(mean_profile, args.max_colors)}
    report = json.dumps({"method": "mean RGB per source-screen row, excluding the centered input image",
                         "aggregate": aggregate, "frames": reports}, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
