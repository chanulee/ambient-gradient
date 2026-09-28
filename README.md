# Ambient Gradient

A client-side image-to-gradient studio. Upload a PNG or JPG, select a scan-based method, and tune scan width, edge softness, and ambient motion. The gradient fills the screen; a control island sits at the right. PNG exports the current frame, SVG exports a static vector gradient, and video records eight seconds of motion as MP4 or WebM when supported by the browser. Grain is not used.

## Scan Stripes: current algorithm

Given source image `I(x,y)`:

1. Downsample it to at most 256 pixels wide and 768 pixels tall, compositing transparent pixels over white.
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

**Scan Width** changes the sampled region. **Edge Softness** is available for Soft Scan and Zen Field. It adjusts the bilateral filter's y radius and color-distance tolerance. The baseline is left intact so it can serve as a direct reference.

## Why Zen looked foggy

The previous Zen pass mixed the source profile with Gaussian-smoothed profiles at σ=2.5% and 12% of image height, reduced chroma by 6%, added a 4% warm-white tint, then layered radial color washes at up to 18% opacity and applied another canvas blur. Those operations explain the pale veil. Zen Field now keeps original chroma and removes the white tint and radial wash; only a 14% broad-scale component remains alongside color-aware smoothing.

## Research context and useful hybrids

- [Tomasi and Manduchi, *Bilateral Filtering for Gray and Color Images* (ICCV 1998)](https://projects.iq.harvard.edu/sites/projects.iq.harvard.edu/files/imagenesmedicas/files/tomasi1998kg.pdf) weights nearby samples by both spatial and color similarity. Soft Scan applies that principle to the 1D scan profile, so small same-color variation calms down while a strong band edge survives.
- [Tan, Echevarria, and Gingold, *Efficient palette-based decomposition and recoloring via RGBXY-space geometry* (SIGGRAPH Asia 2018)](https://cragl.cs.gmu.edu/fastlayers/) jointly considers image color and position. A useful future hybrid is to use its spatial layers to propose a few band candidates, then let Scan Stripes choose/sequence the candidates by y. The current generator does not implement RGBXY convex-hull decomposition.
- [Chang et al., *Palette-based Photo Recoloring* (SIGGRAPH 2015)](https://pixl.cs.princeton.edu/pubs/chang_2015_ppr/index.php) uses an image palette to guide recoloring. Here original-pixel key colors are also kept separate from the scan profile; Accent Scan uses them only as a palette display, while the per-row accent decision comes from local scan pixels.

The practical new direction is **scan first, adjust the signal second**: retain a simple, inspectable y-profile; expose the scan aperture; then add optional chroma-aware selection or edge-aware smoothing. This is an implementation proposal, not a validated perception result. A paper-level novelty claim would need comparisons on varied images and a user study or perceptual metric for stripe continuity, source-color retention, and aesthetic preference.

## Reference screenshot analysis

`analyze_gradient.py` measures average RGB across each screenshot row after excluding the centered source image. That row average is used only to analyze the reference backgrounds; the generator does not use it. The script reports strong transitions, adaptive color groups, and frame-to-frame changes. It requires Pillow.

```sh
python3 analyze_gradient.py frame-1.png frame-2.png frame-3.png \
  --exclude 303,325,697,846 \
  --output original-gradient-analysis.json
```

The included cherry-blossom measurements estimate 5 colors and 6 strong boundaries in the average profile, with 5/8/6 colors and 8–10 boundaries across individual frames. These are screenshot estimates, not recovered original parameters.
