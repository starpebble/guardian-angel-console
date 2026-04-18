"""Optional hex-encoded image → data URI for the transmissions UI."""

from __future__ import annotations

import base64
import binascii


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def hex_to_image_data_uri(hex_blob: str | None) -> str | None:
    """If ``hex_blob`` decodes to JPEG or PNG bytes, return a matching ``data:image/...;base64,...`` URI."""

    if not hex_blob or not isinstance(hex_blob, str):
        return None
    s = hex_blob.strip()
    if s.lower().startswith("hex:"):
        s = s[4:].strip()
    s = s.replace(" ", "").replace("\n", "")
    if len(s) % 2 == 1:
        return None
    try:
        data = binascii.unhexlify(s.encode("ascii"))
    except (binascii.Error, ValueError):
        return None
    if len(data) < 4:
        return None
    if data[:2] == b"\xff\xd8":
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    if len(data) >= 8 and data[:8] == _PNG_MAGIC:
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/png;base64,{b64}"
    return None
