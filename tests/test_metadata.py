"""Keep HACS packaging and release metadata consistent."""

import json
import os
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "adb_app_state"


def test_manifest_and_hacs_metadata():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert manifest["domain"] == "adb_app_state"
    assert manifest["name"] == hacs["name"] == "ADB App State"
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    if (ref := os.environ.get("GITHUB_REF", "")).startswith("refs/tags/"):
        assert ref.removeprefix("refs/tags/v") == manifest["version"]
    assert manifest["codeowners"] == ["@speedy3wk"]
    assert manifest["documentation"] == "https://github.com/speedy3wk/ha-adb-app-state"
    assert manifest["issue_tracker"] == manifest["documentation"] + "/issues"
    assert list((ROOT / "custom_components").glob("*/manifest.json")) == [
        INTEGRATION / "manifest.json"
    ]
    assert (ROOT / "LICENSE").read_text().startswith("MIT License")


def test_brand_png_dimensions():
    for name, dimensions in {
        "icon.png": (256, 256),
        "icon@2x.png": (512, 512),
        "logo.png": (410, 128),
        "logo@2x.png": (820, 256),
    }.items():
        data = (INTEGRATION / "brand" / name).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", data[16:24]) == dimensions


def test_translation_fields_match_source():
    source = json.loads((INTEGRATION / "strings.json").read_text())
    for path in (INTEGRATION / "translations").glob("*.json"):
        translation = json.loads(path.read_text())
        assert translation["config"]["step"]["user"]["data"].keys() == (
            source["config"]["step"]["user"]["data"].keys()
        )
        assert translation["options"]["step"]["init"]["data"].keys() == (
            source["options"]["step"]["init"]["data"].keys()
        )
