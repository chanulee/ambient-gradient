#!/usr/bin/env python3
"""Run reproducible synthetic and reference-photo comparisons for Palette Scan."""

import json
import random
import argparse
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'paper' / 'figures'


def fixture():
    image = Image.new('RGB', (320, 320), '#dedbd7')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 319, 69), fill='#f6f4f0')
    draw.rectangle((0, 70, 319, 119), fill='#c9c5c1')
    draw.rectangle((0, 120, 319, 190), fill='#303438')
    draw.rectangle((0, 191, 319, 255), fill='#aaa6a1')
    draw.rectangle((0, 256, 319, 319), fill='#f2eee8')
    # Accents are present in the image but entirely outside the baseline's center aperture.
    draw.rounded_rectangle((17, 24, 102, 48), radius=7, fill='#ffffff')
    draw.rounded_rectangle((217, 87, 307, 108), radius=7, fill='#baff00')
    draw.rounded_rectangle((24, 205, 117, 226), radius=7, fill='#ff6b00')
    draw.rounded_rectangle((217, 276, 307, 299), radius=7, fill='#baff00')
    return image


def random_fixture(seed):
    rng = random.Random(seed)
    image = Image.new('RGB', (256, 256), '#e8e5df')
    draw = ImageDraw.Draw(image)
    for y0, y1, color in [(0, 51, '#f2efe9'), (52, 102, '#c3c0b9'), (103, 164, '#626568'),
                           (165, 207, '#282d31'), (208, 255, '#aaa49e')]:
        draw.rectangle((0, y0, 255, y1), fill=color)
    for color in ['#ffffff', '#baff00', '#ff6b00']:
        width = rng.randint(36, 104)
        height = rng.randint(5, 18)
        x = rng.choice([rng.randint(2, 34), rng.randint(145, max(145, 252-width))])
        y = rng.randint(8, 238-height)
        draw.rectangle((x, y, x+width, y+height), fill=color)
    return image


def resized_rgba(image):
    scale = min(1, 768 / max(image.size))
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return np.asarray(image.convert('RGBA').resize(size, Image.Resampling.LANCZOS), dtype=np.uint8)


def run_core(pixels, config=None, palette_pixels=None):
    h, w, _ = pixels.shape
    palette_pixels = pixels if palette_pixels is None else palette_pixels
    palette_h, palette_w, _ = palette_pixels.shape
    start = time.perf_counter()
    result = subprocess.run(
        ['node', str(ROOT / 'experiments' / 'project.cjs')],
        input=json.dumps({'width': w, 'height': h, 'pixels': pixels.reshape(-1).tolist(),
                          'paletteWidth': palette_w, 'paletteHeight': palette_h, 'palettePixels': palette_pixels.reshape(-1).tolist(),
                          'scanWidth': 12, 'config': config or {}}),
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    elapsed = time.perf_counter() - start
    output = json.loads(result.stdout)
    output['elapsed_s'] = elapsed
    output['scan'] = np.asarray(output['scan'], dtype=np.uint8).reshape(h, 4)
    output['projected'] = np.asarray(output['projected'], dtype=np.uint8).reshape(h, 4)
    output['palette'] = [tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5)) for hex_color in output['palette']]
    return output


def lab(rgb):
    rgb = np.asarray(rgb, dtype=np.float64) / 255
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    l = np.cbrt(.4122214708*linear[..., 0] + .5363325363*linear[..., 1] + .0514459929*linear[..., 2])
    m = np.cbrt(.2119034982*linear[..., 0] + .6806995451*linear[..., 1] + .1073969566*linear[..., 2])
    s = np.cbrt(.0883024619*linear[..., 0] + .2817188376*linear[..., 1] + .6299787005*linear[..., 2])
    return np.stack((.2104542553*l + .793617785*m - .0040720468*s,
                     1.9779984951*l - 2.428592205*m + .4505937099*s,
                     .0259040371*l + .7827717662*m - .808675766*s), axis=-1)


def memberships(colors, palette):
    distances = np.linalg.norm(lab(colors)[..., None, :] - lab(palette)[None, ...], axis=-1)
    logits = -(distances ** 2) / (2 * .055 ** 2)
    logits -= logits.max(axis=-1, keepdims=True)
    weights = np.exp(logits)
    return weights / np.maximum(weights.sum(axis=-1, keepdims=True), 1e-12)


def metrics(source, profile, palette):
    source_weights = memberships(source[:, :, :3].reshape(-1, 3), palette)
    profile_weights = memberships(profile[:, :3], palette)
    source_hist = source_weights.mean(axis=0)
    output_hist = profile_weights.mean(axis=0)
    source_rows = source_weights.reshape(source.shape[0], source.shape[1], -1).mean(axis=1)
    output_rows = profile_weights
    source_distributions = source_rows / np.maximum(source_rows.sum(axis=0, keepdims=True), 1e-12)
    output_distributions = output_rows / np.maximum(output_rows.sum(axis=0, keepdims=True), 1e-12)
    w1 = np.abs(np.cumsum(source_distributions, axis=0) - np.cumsum(output_distributions, axis=0)).sum(axis=0) / max(source.shape[0]-1, 1)
    masses = source_hist / max(source_hist.sum(), 1e-12)
    vertical_w1 = float(np.sum(w1 * masses))
    accents = []
    for index, color in enumerate(palette):
        normalized = color / 255
        saturation = (normalized.max()-normalized.min()) / max(normalized.max(), 1e-12)
        if normalized.max() > .78 and saturation > .28 and source_hist[index] >= .00015:
            accents.append(index)
    delta = np.linalg.norm(np.diff(lab(profile[:, :3]), axis=0), axis=1)
    return {
        'palette_share_tv': float(.5*np.abs(source_hist-output_hist).sum()),
        'vertical_distribution_w1': vertical_w1,
        'accent_recall': float(sum(np.min(np.linalg.norm(lab(profile[:, :3])-lab(palette[i]), axis=1)) < .075 for i in accents) / max(1, len(accents))),
        'mean_adjacent_deltaE_ok': float(delta.mean()) if len(delta) else 0,
        'strong_transitions_deltaE_gt_0_08': int((delta > .08).sum()),
        'supported_neon_palette_colors': len(accents),
    }


def stripe_image(profile, width=700):
    return Image.fromarray(np.repeat(profile[None, :, :3], width, axis=0).transpose(1, 0, 2)).resize((width, 480), Image.Resampling.BICUBIC)


def comparison_figure(cases):
    figure = Image.new('RGB', (1320, 700), '#f4f2ed')
    draw = ImageDraw.Draw(figure)
    labels = [('SOURCE', 25), ('SCAN STRIPES', 275), ('PALETTE SCAN', 800)]
    for label, x in labels: draw.text((x, 8), label, fill='#4b4b47')
    for row, (name, image, scan, projected) in enumerate(cases):
        top = 35 + row*330
        draw.text((25, top), 'Synthetic accents' if name == 'synthetic_accents' else 'Phone photograph', fill='#66645f')
        source_box = ImageOps.contain(image.convert('RGB'), (210, 275), Image.Resampling.LANCZOS)
        source_x = 130 - source_box.width//2
        figure.paste(source_box, (source_x, top+28))
        for profile, x in ((scan, 275), (projected, 800)):
            strip = Image.fromarray(profile[:, :3].reshape(profile.shape[0], 1, 3)).resize((490, 275), Image.Resampling.BICUBIC)
            figure.paste(strip, (x, top+28))
            draw.rectangle((x, top+28, x+489, top+302), outline='#d2d0c9', width=1)
    return figure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, help='optional real photo; 25 synthetic cases always run')
    args = parser.parse_args()
    if args.image and not args.image.is_file():
        parser.error(f'image does not exist: {args.image}')
    OUT.mkdir(parents=True, exist_ok=True)
    synthetic = [('synthetic_accents', fixture())] + [(f'synthetic_{index:02d}', random_fixture(index)) for index in range(24)]
    cases = synthetic + ([('reference_photo', Image.open(args.image))] if args.image else [])
    reports, panel_rows, synthetic_metrics, ablation_inputs, figure_cases = [], [], [], [], []
    for name, image in cases:
        source = resized_rgba(image)
        palette_scale = min(1, 192/max(image.size))
        palette_size = (max(1, round(image.width*palette_scale)), max(1, round(image.height*palette_scale)))
        palette_source = resized_rgba(image.resize(palette_size, Image.Resampling.LANCZOS))
        output = run_core(source, palette_pixels=palette_source)
        palette = np.asarray(output['palette'], dtype=np.float64)
        baseline_metrics = metrics(source, output['scan'], palette)
        proposed_metrics = metrics(source, output['projected'], palette)
        if name.startswith('synthetic_') or name == 'synthetic_accents':
            synthetic_metrics.append((baseline_metrics, proposed_metrics))
        reports.append({'case': name, 'input_size': list(image.size), 'processing_size': [source.shape[1], source.shape[0]],
                        'palette': [('#' + ''.join(f'{c:02X}' for c in color)) for color in output['palette']],
                        'baseline': baseline_metrics, 'palette_scan': proposed_metrics,
                        'projector_wall_time_seconds': round(output['elapsed_s'], 3)})
        if name in ('synthetic_accents', 'synthetic_00', 'synthetic_01', 'synthetic_02', 'synthetic_03', 'reference_photo'):
            ablation_inputs.append((name, source, palette, palette_source))
        if name in ('synthetic_accents', 'reference_photo'):
            figure_cases.append((name, image, output['scan'], output['projected']))
            thumb = image.convert('RGB').resize((240, 240), Image.Resampling.LANCZOS)
            strip_a = stripe_image(output['scan']).resize((480, 180))
            strip_b = stripe_image(output['projected']).resize((480, 180))
            panel = Image.new('RGB', (740, 520), '#efede8')
            panel.paste(thumb, (10, 10)); panel.paste(strip_a, (250, 30)); panel.paste(strip_b, (250, 280))
            draw = ImageDraw.Draw(panel)
            draw.text((250, 10), f'{name}: Scan Stripes', fill='#222')
            draw.text((250, 260), 'Palette Scan', fill='#222')
            panel_rows.append(panel)
            Image.fromarray(output['scan'][:, :3].reshape(source.shape[0], 1, 3)).resize((900, 320), Image.Resampling.BICUBIC).save(OUT / f'{name}-scan.png')
            Image.fromarray(output['projected'][:, :3].reshape(source.shape[0], 1, 3)).resize((900, 320), Image.Resampling.BICUBIC).save(OUT / f'{name}-palette.png')
    sheet = Image.new('RGB', (740, 1040), '#efede8')
    for index, panel in enumerate(panel_rows): sheet.paste(panel, (0, index*520))
    sheet.save(OUT / 'comparison.png')
    comparison_figure(figure_cases).save(OUT / 'comparison-wide.png')
    keys = synthetic_metrics[0][0].keys()
    aggregate = {'synthetic_cases': len(synthetic_metrics), 'baseline_mean': {key: float(np.mean([base[key] for base, _ in synthetic_metrics])) for key in keys},
                 'palette_scan_mean': {key: float(np.mean([new[key] for _, new in synthetic_metrics])) for key in keys}}
    reports.append({'aggregate': aggregate})
    ablations = {'no_mass_constraint': {'preserveMass': False},
                 'no_scan_anchor': {'evidencePower': 1, 'scanPower': 0, 'scanResidual': 0},
                 'no_vertical_evidence': {'evidencePower': 0, 'scanPower': 1, 'scanResidual': 0},
                 'no_continuity_penalty': {'transitionCost': 0},
                 'no_accent_visibility_floor': {'visibilityRows': 0}}
    ablation_summary = {}
    for variant, config in ablations.items():
        results = []
        for name, source, palette, palette_source in ablation_inputs:
            output = run_core(source, config, palette_source)
            results.append(metrics(source, output['projected'], palette))
        ablation_summary[variant] = {'n': len(results), **{key: float(np.mean([result[key] for result in results])) for key in results[0]}}
    reports.append({'ablations': ablation_summary})
    (ROOT / 'paper' / 'experiment-results.json').write_text(json.dumps(reports, indent=2) + '\n')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
