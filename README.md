# Ambient Gradient

A client-side image-to-gradient studio. Upload a PNG or JPG, select a scan-based method, and tune scan width, edge softness, and ambient motion. The gradient fills the screen; a control island sits at the right. PNG exports the current frame, SVG exports a static vector gradient, and video records eight seconds of motion as MP4 or WebM when supported by the browser. Grain is not used.

## Scan Stripes: current algorithm

Given source image `I(x,y)`:

1. Downsample it proportionally so its longer side is at most 768 pixels, compositing transparent pixels over white.
2. At each source row `y`, inspect only a centered vertical window. Its width is controlled by **Scan Width** (default 12% of the image width).
3. Quantize each inspected RGB pixel into a 4-bit-per-channel bucket (4096 possible bins), then choose the most populated bin for that row. The output color is the mean of pixels inside that one winning bin. This is a row-local histogram mode, not a row-wide average and not a global palette clustering.
4. Write those colors to a 1×H profile. This retains source y order but makes each row's choice independently, so quantization can create thin edges and jitter.
5. Animate six overlapping y zones with low-amplitude local brightness and tint shifts. **Smooth** applies a small canvas blur; **Pixel** reduces the output height according to Pixel Detail.

In pseudocode:

```text
for y in 0..H:
    bins = histogram(quantize4(I[x,y]) for x in centerWindow)
    P[y] = mean(original RGB pixels in argmax_count(bins))
```

## Scan variants

| Method | What changes from Scan Stripes | Source / signal-processing idea |
| --- | --- | --- |
| **Scan Stripes** | Baseline per-row mode; strongest fidelity to the current result | Color histogram mode |
| **Soft Scan** | Filters the 1D profile using both y distance and OKLab color distance; nearby similar colors merge, large color jumps keep their edge | Bilateral filtering |
| **Accent Scan** | Keeps the dominant row mode, then mixes in a separated vivid local mode in proportion to its presence in the scan window | Palette-aware local histogram selection |
| **Zen Field** | A modest edge-aware scan plus a small broad-scale component. It does not whiten, desaturate, add glow, or bloom | Multiscale signal decomposition with restrained amplitude |
| **Color Story** | Orders original-image key colors by their vertical centers and makes a designed transition sequence | Spatial palette summary; deliberately changes source proportions |
| **Palette Scan** | Balances the full-image key-colour proportions against where those colours occur vertically, then projects them back into a scan profile | Palette-mass-constrained scanline projection (prototype) |

**Scan Width** changes the sampled region. **Edge Softness** is available for Soft Scan and Zen Field. It adjusts the bilateral filter's y radius and color-distance tolerance. The baseline is left intact so it can serve as a direct reference.

## Why Zen looked foggy

The previous Zen pass mixed the source profile with Gaussian-smoothed profiles at σ=2.5% and 12% of image height, reduced chroma by 6%, added a 4% warm-white tint, then layered radial color washes at up to 18% opacity and applied another canvas blur. Those operations explain the pale veil. Zen Field now keeps original chroma and removes the white tint and radial wash; only a 14% broad-scale component remains alongside color-aware smoothing.

## Research context and useful hybrids

- [Tomasi and Manduchi, *Bilateral Filtering for Gray and Color Images* (ICCV 1998)](https://projects.iq.harvard.edu/sites/projects.iq.harvard.edu/files/imagenesmedicas/files/tomasi1998kg.pdf) weights nearby samples by both spatial and color similarity. Soft Scan applies that principle to the 1D scan profile, so small same-color variation calms down while a strong band edge survives.
- [Tan, Echevarria, and Gingold, *Efficient palette-based decomposition and recoloring via RGBXY-space geometry* (SIGGRAPH Asia 2018)](https://cragl.cs.gmu.edu/fastlayers/) jointly considers image color and position. A useful future hybrid is to use its spatial layers to propose a few band candidates, then let Scan Stripes choose/sequence the candidates by y. The current generator does not implement RGBXY convex-hull decomposition.
- [Chang et al., *Palette-based Photo Recoloring* (SIGGRAPH 2015)](https://pixl.cs.princeton.edu/pubs/chang_2015_ppr/index.php) uses an image palette to guide recoloring. Here original-pixel key colors are also kept separate from the scan profile; Accent Scan uses them only as a palette display, while the per-row accent decision comes from local scan pixels.

The practical new direction is **scan first, adjust the signal second**: retain a simple, inspectable y-profile; expose the scan aperture; then add chroma-aware palette projection or edge-aware smoothing. Palette Scan below is a prototype with initial objective comparisons. Those measurements do not establish aesthetic preference or broad perceptual validity.

## Palette Scan: projection operator prototype

`PALETTE SCAN` is the candidate research method. It keeps the existing central Scan Stripes profile as a structural anchor, while deriving palette evidence from the whole image:

1. Extract key colours from the source image independently of the scan profile. For every processing pixel, compute soft assignments to those colours in OKLab. Their full-image masses are `q[k]`; their row-wise evidence is `r[y,k]`.
2. Combine row evidence with similarity to the original scan colour. Sinkhorn scaling balances the resulting row-by-palette matrix so every row has unit mass and its colour columns match `q`.
3. Convert soft assignments to one colour per output row. A 1D Potts path cost favors continuous runs; boundary evidence from changes in source row colours or the scan profile lowers that cost where a transition is supported. Largest-remainder apportionment enforces integer row quotas. Bright, saturated key colours with enough source support receive a four-row minimum; the added rows are taken proportionally from the other colours.
4. Reconstruct a short OKLab transition around label changes and add 42% of the scan profile's residual relative to the nearest palette colour. This keeps fine changes from Scan Stripes while making off-center image colours available to the output.

The minimum accent width trades exact source proportion for visibility. Smoothing the final transition also changes the rendered pixel histogram slightly, so the exact quota guarantee applies to discrete row labels before reconstruction. The operator is a task-specific hybrid of palette balancing, scanline evidence, and 1D total-variation regularization; those components are established ideas. The contribution claim should remain limited to this formulation and must be tested against broader prior work before calling it a novel general-purpose filter.

## Reproducing the prototype experiments

The experiment runner calls the same JavaScript projector used by the browser app. It generates 25 fixed-seed synthetic scenes with off-center white, lime, and orange patches, optionally processes a real photograph, and reports palette-mass total variation, vertical-distribution Wasserstein distance, accent recall, adjacent OKLab change, and strong-transition count. Five ablations remove mass balancing, the scan anchor, vertical evidence, continuity cost, and the minimum accent width. No human preference or aesthetic-quality claim is measured.

```sh
python3 experiments/run_experiments.py
python3 experiments/run_experiments.py --image /path/to/photo.png
```

The measured reference-phone run uses the supplied `TL_Preview.png`. Results are saved in `paper/experiment-results.json`; visual comparisons are in `paper/figures/comparison-wide.png`. On 25 synthetic cases, mean palette-share TV changed from 0.0370 to 0.0196, normalized vertical W1 from 0.0176 to 0.0160, and eligible accent recall from 0.02 to 0.80. Strong transitions increased from 4.08 to 10.92 per profile, exposing the continuity trade-off. On the single real photo, palette-share TV changed from 0.0847 to 0.0323 and vertical W1 from 0.0998 to 0.0985. One photo is not enough to claim generalization.

## Reference screenshot analysis

`analyze_gradient.py` measures average RGB across each screenshot row after excluding the centered source image. That row average is used only to analyze the reference backgrounds; the generator does not use it. The script reports strong transitions, adaptive color groups, and frame-to-frame changes. It requires Pillow.

```sh
python3 analyze_gradient.py frame-1.png frame-2.png frame-3.png \
  --exclude 303,325,697,846 \
  --output original-gradient-analysis.json
```

The included cherry-blossom measurements estimate 5 colors and 6 strong boundaries in the average profile, with 5/8/6 colors and 8–10 boundaries across individual frames. These are screenshot estimates, not recovered original parameters.
