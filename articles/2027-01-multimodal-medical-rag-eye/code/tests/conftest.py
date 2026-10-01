import csv
import io

from eye_rag.labels import CODES, DISEASE_RISK


def make_csv(rows: list[tuple[int, set[str]]]) -> str:
    """A synthetic RFMiD-style label CSV: (image number, condition codes)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", DISEASE_RISK, *CODES])
    for n, labels in rows:
        w.writerow([n, int(bool(labels)), *[int(c in labels) for c in CODES]])
    return "﻿" + buf.getvalue()
