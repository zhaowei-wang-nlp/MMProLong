"""Smaller image transport with exact decoded RGBA pixels and page dimensions."""

import base64
import hashlib
import io
import os
import threading
from pathlib import Path

from PIL import Image

_locks = [threading.Lock() for _ in range(64)]
_enabled = False


def configure(enabled):
    global _enabled
    _enabled = bool(enabled)


def encode_image(data, cache):
    digest = hashlib.sha256(data).hexdigest()
    cache = Path(cache)
    target = cache / (digest + ".webp")
    unchanged = cache / (digest + ".original")
    with _locks[int(digest[:8], 16) % len(_locks)]:
        if target.exists():
            return "image/webp", target.read_bytes()
        with Image.open(io.BytesIO(data)) as original:
            mime = Image.MIME.get(original.format, "image/png")
            if unchanged.exists():
                return mime, data
            # Do not reinterpret animation, EXIF orientation or color profiles.
            if (getattr(original, "n_frames", 1) != 1 or original.info.get("icc_profile") or original.getexif()
                    or original.mode not in {"RGB", "RGBA", "L", "LA", "P", "1"}):
                return mime, data
            pixels = original.convert("RGBA")
            output = io.BytesIO()
            pixels.save(output, format="WEBP", lossless=True, method=3, exact=True)
            packed = output.getvalue()
            if len(packed) < len(data):
                with Image.open(io.BytesIO(packed)) as check:
                    if check.size != pixels.size or check.convert("RGBA").tobytes() != pixels.tobytes():
                        raise ValueError("Lossless image transport changed decoded pixels")
                cache.mkdir(parents=True, exist_ok=True)
                temp = target.with_suffix(f".{os.getpid()}.tmp")
                temp.write_bytes(packed)
                temp.replace(target)
                return "image/webp", packed
            cache.mkdir(parents=True, exist_ok=True)
            unchanged.touch()
            return mime, data


def image_url(path, cache):
    data = Path(path).read_bytes()
    mime, data = encode_image(data, cache) if _enabled else ("image/png", data)
    return "data:" + mime + ";base64," + base64.b64encode(data).decode()


def optimize_blocks(messages, cache):
    if not _enabled:
        return
    for message in messages:
        if not isinstance(message.get("content"), list):
            continue
        for block in message["content"]:
            if block.get("type") != "image_url":
                continue
            url = block["image_url"]["url"]
            if not url.startswith("data:image/") or ";base64," not in url:
                continue
            data = base64.b64decode(url.split(";base64,", 1)[1])
            mime, packed = encode_image(data, cache)
            block["image_url"]["url"] = "data:" + mime + ";base64," + base64.b64encode(packed).decode()
