# Images

All images here are **synthetic**, rendered by this article's generator (`code/`), and watermarked "AMOSTRA • SYNTHETIC" / "SEM VALOR LEGAL". Names, numbers and dates are generated; no real person's data and no real document. No BID Dataset images are included (BID is cited, not redistributed).

- `synthetic-cnh-round1-vs-round2.jpg`: the figure in the articles. Top: round 1 (one design). Bottom: round 2 (palettes, fonts, boxed fields, scans, rotations varied). Round 3 uses the same images as round 2.
- `reader-extractor.en.svg` / `reader-extractor.pt-br.svg`: the Reader + Extractor pipeline diagram in the articles (EN drafts and PT-BR draft). `reader-extractor.en.png` / `reader-extractor.pt-br.png` are the same diagrams as PNG (light theme); Medium does not render SVG, so upload the PNG there by hand. Sources: `diagrams/reader-extractor.en.dataflow.json` and `diagrams/reader-extractor.pt-br.dataflow.json`. Made with [archify](https://github.com/tt-a1i/archify) (MIT) from the article's own content; these are drawings, not document images.

## samples/

Single test-set images, as the models saw them:

| File | Set | What it shows |
|---|---|---|
| `round1-cnh-clean.jpg` | round 1 test (`data/synth/test`, test-00277) | printed CNH, clean |
| `round1-cnh-photo.jpg` | round 1 test (test-00051) | printed CNH, photographed at an angle |
| `round2-cnh-blue-phone.jpg` | round 2/3 test (`data/synth-v2/test`, test-s03-00001) | different palette and boxed fields, phone photo, hard |
| `round2-cnh-gray-scan.jpg` | round 2/3 test (test-s02-00008) | gray palette, monospace font, flatbed scan |
| `round2-cnh-scan-rotated-270.jpg` | round 2/3 test (test-s03-00023) | scan turned 270° |
| `round2-cnh-digital-screenshot.jpg` | round 2/3 test (test-s08-00027) | CNH Digital app screenshot with QR code |
| `round2-decoy-rg.jpg` | round 2/3 test (test-s00-00000) | decoy: an RG card in the same style |
| `hard-cnh-dark-angled.jpg` | hard set (`data/synth-hard/test`, test-00076) | dark, strongly angled photo |
| `hard-decoy-invoice.jpg` | hard set (test-00071) | decoy: a skewed invoice (nota fiscal) |
