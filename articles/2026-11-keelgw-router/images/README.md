# Images

`router.en.svg` and `router.en.png` are exports of one diagram made with
[archify](https://github.com/tt-a1i/archify) (MIT). They carry no fact or
number that isn't in the code README.

| File | What it is |
|---|---|
| `diagrams/router.en.dataflow.json` | The diagram's source |
| `diagrams/router.en.html` | The interactive version: pan, zoom, light and dark |
| `router.en.svg` | Used by the README; follows the reader's light or dark theme |
| `router.en.png` | For places that don't render SVG |

To change it: edit the JSON, validate with
`archify validate dataflow diagrams/router.en.dataflow.json --quality showcase`,
render it with `archify deliver`, then export the SVG and PNG from the HTML's
Export menu.
