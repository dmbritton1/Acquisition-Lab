"""Writes a minimal valid PDF by hand, so tests need no PDF library to make one."""
from pathlib import Path


def write_pdf(path: Path, pages: list[str | None]) -> Path:
    """One page per entry; None makes a page with an empty stream (an image-only page)."""
    n = len(pages)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % (4 + 2 * i) for i in range(n)) + b"] /Count %d >>" % n,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, text in enumerate(pages):
        body = b"" if text is None else b"BT /F1 12 Tf 72 720 Td (%s) Tj ET" % text.encode()
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
                    b"/Resources << /Font << /F1 3 0 R >> >> >>" % (5 + 2 * i))
        objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(body), body))
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, o)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(out)
    return path
