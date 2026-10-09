# Images

## Pipeline diagram

| File | What |
|---|---|
| `pipeline.en.svg` / `pipeline.en.png` | The pipeline, English. Used in `article-en.md`. |
| `pipeline.pt-br.svg` / `pipeline.pt-br.png` | The same, Brazilian Portuguese. Used in `article-pt-br.md`. |
| `diagrams/pipeline.en.dataflow.json`, `diagrams/pipeline.pt-br.dataflow.json` | Sources. |

Made with [archify](https://github.com/tt-a1i/archify) v2.16.0 (MIT) from the article's own content: validated at the `showcase` profile, then exported to SVG through the viewer's own export. The PNGs are the light-theme render of the same SVG. Medium does not render SVG: upload the PNG there by hand.

## Retinal photographs

| File | What |
|---|---|
| `test-205-query-and-retrieved-cases.jpg` | Left: RFMiD test image 205 (the query in the article's worked example). Right: its three retrieved training cases, in retrieval order (training images 1693, 1561, 976). Used in the EN, Medium and PT-BR articles. |

Source: RFMiD 1.0, S. Pachade et al., *Retinal Fundus Multi-Disease Image Dataset (RFMiD)*, Data 2021, 6(2), 14, doi:10.3390/data6020014, CC BY 4.0 (see `code/docs/DATA.md` for the licence note that is still to confirm on the official page). Changes: square-cropped, resized and placed side by side; no text added. These four thumbnails are the only retinal images in git, as the plan allows ("at most a few attributed thumbnails in the article"); the dataset itself stays out of the repo.
