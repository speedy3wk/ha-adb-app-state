from __future__ import annotations

import io
import re
import zipfile
from collections import Counter


def iter_zip_entry_bytes(
    zip_bytes: bytes,
    *,
    max_files: int = 15,
    max_bytes_per_file: int = 100_000,
) -> list[bytes]:
    if not zip_bytes:
        return []

    out: list[bytes] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            for name in names[:max_files]:
                try:
                    raw = zf.read(name)
                except Exception:  # noqa: BLE001
                    continue
                if not raw:
                    continue
                out.append(raw[:max_bytes_per_file])
    except Exception:  # noqa: BLE001
        return []

    return out


def parse_visible_components_from_window_views_zip(zip_bytes: bytes) -> list[str]:
    """Extract component strings from ZIP entry names.

    Some devices include the component in the ZIP filename even if the payload is empty.
    """

    if not zip_bytes:
        return []

    comps: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                for part in name.split():
                    if "/" in part and "." in part:
                        comps.append(part.strip())
                        break
    except Exception:  # noqa: BLE001
        return []

    seen: set[str] = set()
    out: list[str] = []
    for c in comps:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


_VIEW_DUMP_RESOURCE_PKG_RE = re.compile(rb"([a-zA-Z0-9_\.]{3,200}):id/")


def _normalize_view_dump_pkg(raw: str) -> str:
    if raw.startswith("__attr__"):
        raw = raw[len("__attr__") :]
    return raw


def parse_package_counts_from_window_views_zip(zip_bytes: bytes) -> dict[str, int]:
    if not zip_bytes:
        return {}

    counts: Counter[str] = Counter()
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                data = zf.read(name)
                for m in _VIEW_DUMP_RESOURCE_PKG_RE.finditer(data):
                    pkg = _normalize_view_dump_pkg(
                        m.group(1).decode("utf-8", errors="ignore")
                    )
                    if pkg:
                        counts[pkg] += 1
    except Exception:  # noqa: BLE001
        return {}

    return dict(counts)


def parse_primary_package_from_window_views_zip(
    zip_bytes: bytes,
    *,
    ignore_packages: set[str] | None = None,
) -> str | None:
    """Best-effort primary app package from visible window views ZIP."""

    counts = parse_package_counts_from_window_views_zip(zip_bytes)
    if not counts:
        comps = parse_visible_components_from_window_views_zip(zip_bytes)
        if not comps:
            return None
        pkg = comps[0].split("/", 1)[0]
        pkg = _normalize_view_dump_pkg(pkg)
        return pkg or None

    ignore = ignore_packages or set()
    filtered = {k: v for k, v in counts.items() if k not in ignore}
    if not filtered:
        return None

    return max(filtered.items(), key=lambda kv: kv[1])[0]
