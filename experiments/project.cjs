const fs = require('node:fs');
const projection = require('../palette-projection.js');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const pixels = new Uint8ClampedArray(input.pixels);
const palettePixels = input.palettePixels ? new Uint8ClampedArray(input.palettePixels) : pixels;
const palette = projection.extractColors(palettePixels, input.paletteWidth || input.width, input.paletteHeight || input.height);
const scan = projection.scanProfile(pixels, input.width, input.height, input.scanWidth || 12);
const result = projection.project(pixels, input.width, input.height, palette, scan, input.config || {});
process.stdout.write(JSON.stringify({ palette, scan: Array.from(scan), projected: Array.from(result) }));
