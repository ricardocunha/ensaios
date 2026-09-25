"""Turn the BID Dataset (Soares, Junior & Bezerra, SIBGRAPI 2020) into a Reader test split.

    make bid     # download the sample, then:
    uv run python -m cnh_ocr.evaluation.bid --bid "data/bid-raw/BID Sample Dataset" --out data/bid

BID has no license and is not redistributed here (ADR-0002); `data/` is gitignored.
BID images are synthetic, generated from anonymized real documents, so they are not
Private Real Samples. Each image has a `*_gt_ocr.txt` CSV of text regions with boxes. File order is not
reliable (a value sometimes precedes its label), so each value is paired with its
label by format and by distance. Only the 8 fields that can be paired unambiguously are
scored: NOME, CPF, DATA NASCIMENTO, CAT. HAB., Nº REGISTRO, VALIDADE,
1ª HABILITAÇÃO, plus LOCAL and DATA EMISSÃO on the open (Aberta) card.
CNH_Frente / CNH_Aberta become CNH tests; RG_Frente / CPF_Frente become Non-CNH tests.

Caveat: BID dates are random (e.g. born 2019, valid until 2007). That's fine for the
Reader, but useless for the Extractor's date checks.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import unicodedata
from pathlib import Path

from .. import transcription as tx

CNH_CLASSES = ("CNH_Frente", "CNH_Aberta")
NON_CNH_CLASSES = ("RG_Frente", "CPF_Frente")
_UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


def _key(text: str) -> str:
    """Accent-, space- and punctuation-insensitive form, for matching printed labels."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", text.upper())


# Our label -> the key of how BID prints it (spelling varies slightly: "ÓRG EMISSOR", "N°").
_LABEL_KEYS = {_key(label): label for label in tx.LABELS}
_LABEL_KEYS[_key("DOC. IDENTIDADE/ÓRG EMISSOR UF")] = "DOC. IDENTIDADE / ÓRG. EMISSOR / UF"
_LABEL_KEYS[_key("1º HABILITAÇÃO")] = "1ª HABILITAÇÃO"


BOILERPLATE = {_key(t) for t in (
    "ASSINATURA DO PORTADOR", "ASSINATURA DO EMISSOR", "VÁLIDA EM TODO", "O TERRITÓRIO NACIONAL",
    "PROIBIDO PLASTIFICAR", "DEPARTAMENTO NACIONAL DE TRÂNSITO", "MINISTÉRIO DAS CIDADES",
    "CARTEIRA NACIONAL DE HABILITAÇÃO", "REPÚBLICA FEDERATIVA DO BRASIL", "REPÚBLICA FEDERATIVA DO BRA",
)}

# Only fields whose values can be matched unambiguously (by format, or by being the nearest
# free-text region). FILIAÇÃO / DOC. IDENTIDADE / OBSERVAÇÕES are split across lines
# inconsistently in BID and are not scored.
_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
MATCHERS = {
    "CPF": re.compile(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$").match,
    "Nº REGISTRO": re.compile(r"^\d{11}$").match,
    "CAT. HAB.": re.compile(r"^(A|B|C|D|E|AB|AC|AD|AE)$").match,
    "DATA NASCIMENTO": _DATE.match, "VALIDADE": _DATE.match,
    "1ª HABILITAÇÃO": _DATE.match, "DATA EMISSÃO": _DATE.match,
    "NOME": lambda t: re.fullmatch(r"[A-ZÀ-Ý' ]{5,}", t) is not None,
    "LOCAL": re.compile(r"^[A-ZÀ-Ý' ]+\s*-\s*[A-Z]{2}$").match,
}


_POLY = re.compile(r"^\[([^\]]*)\],\s*\[([^\]]*)\],\s*-?\d+,\s*-?\d+,\s*(.*)$")
_BOX = re.compile(r"^(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(.*)$")


def read_regions(path: Path) -> list[tuple[str, float, float]]:
    """(text, center_x, center_y) per region.

    BID uses two formats: `x, y, width, height, text` boxes, and rotated quads written
    as `[x1..x4], [y1..y4], -1, -1, text`. For quads we use the polygon center.
    """
    out = []
    for line in path.read_bytes().decode("latin-1").splitlines()[1:]:
        if m := _POLY.match(line.strip()):
            xs = [float(v) for v in m[1].split(",")]
            ys = [float(v) for v in m[2].split(",")]
            text, cx, cy = m[3], sum(xs) / len(xs), sum(ys) / len(ys)
        elif m := _BOX.match(line.strip()):
            x, y, w, h = map(float, m.groups()[:4])
            text, cx, cy = m[5], x + w / 2, y + h / 2
        else:
            continue
        if text.strip():
            out.append((text.strip(), cx, cy))
    return out


def pair_values(regions: list[tuple[str, float, float]]) -> dict[str, str]:
    labels = {}
    for text, a, b in regions:
        label = _LABEL_KEYS.get(_key(text))
        if label:
            labels[label] = (a, b)
    free = [(t, a, b) for t, a, b in regions if _key(t) not in _LABEL_KEYS and _key(t) not in BOILERPLATE]
    # Greedy global matching: closest (label, value) pairs first, each used once.
    pairs = sorted(
        ((a - la) ** 2 + (b - lb) ** 2, label, i)
        for label, (la, lb) in labels.items() if label in MATCHERS
        for i, (t, a, b) in enumerate(free) if MATCHERS[label](t)
    )
    values, used = {}, set()
    for _, label, i in pairs:
        if label not in values and i not in used:
            values[label] = free[i][0]
            used.add(i)
    return values


def to_transcription(regions: list[tuple[str, float, float]]) -> str:
    values = pair_values(regions)
    return "\n".join(f"{label}: {values[label]}" for label in tx.LABELS if label in values)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bid", type=Path, required=True, help="extracted 'BID Sample Dataset' (or full) folder")
    p.add_argument("--out", type=Path, default=Path("data/bid"))
    args = p.parse_args()

    split = args.out / "test"
    (split / "images").mkdir(parents=True, exist_ok=True)
    n = 0
    with (split / "metadata.jsonl").open("w", encoding="utf-8") as meta:
        for cls in CNH_CLASSES + NON_CNH_CLASSES:
            for img in sorted((args.bid / cls).glob("*_in.jpg")):
                is_cnh = cls in CNH_CLASSES
                name = f"images/{cls}-{img.name}"
                shutil.copyfile(img, split / name)
                answer = to_transcription(read_regions(img.with_name(img.name.replace("_in.jpg", "_gt_ocr.txt")))) \
                    if is_cnh else tx.NOT_A_CNH
                meta.write(json.dumps({
                    "file_name": name, "question": tx.READER_PROMPT, "answer": answer,
                    "kind": "cnh" if is_cnh else "non_cnh", "formato": "fisica" if is_cnh else "",
                    "record": "", "difficulty": f"bid:{cls}",
                }, ensure_ascii=False) + "\n")
                n += 1
    print(f"wrote {n} BID images -> {split}")


if __name__ == "__main__":
    main()
