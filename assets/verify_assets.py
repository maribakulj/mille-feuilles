#!/usr/bin/env python3
"""Vérifie localement le catalogue, les droits archivés et les glyphes réels.

Bibliothèque standard seulement. Aucun téléchargement ni lecture de corpus.
Usage : python3 assets/verify_assets.py [--report assets/coverage.json]
Le contrôle cmap ignore explicitement le glyphe manquant (index zéro).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import unicodedata
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tables(data: bytes) -> dict[str, tuple[int, int]]:
    count = struct.unpack_from(">H", data, 4)[0]
    result = {}
    for index in range(count):
        tag, _, offset, length = struct.unpack_from(">4sIII", data, 12 + 16 * index)
        result[tag.decode("ascii")] = (offset, length)
    return result


def names(data: bytes) -> dict[int, str]:
    offset, _ = tables(data)["name"]
    _, count, storage = struct.unpack_from(">HHH", data, offset)
    result = {}
    for index in range(count):
        platform, _, language, name_id, length, position = struct.unpack_from(
            ">HHHHHH", data, offset + 6 + 12 * index
        )
        raw = data[offset + storage + position:offset + storage + position + length]
        if platform == 3 and language in (0, 0x409):
            result[name_id] = raw.decode("utf-16-be")
        elif platform == 1 and name_id not in result:
            result[name_id] = raw.decode("mac-roman")
    return result


def unicode_cmap(data: bytes) -> set[int]:
    offset, _ = tables(data)["cmap"]
    _, count = struct.unpack_from(">HH", data, offset)
    codepoints = set()
    for index in range(count):
        platform, encoding, relative = struct.unpack_from(">HHI", data, offset + 4 + 8 * index)
        if platform != 0 and not (platform == 3 and encoding in (1, 10)):
            continue
        sub = offset + relative
        fmt = struct.unpack_from(">H", data, sub)[0]
        if fmt == 4:
            segments = struct.unpack_from(">H", data, sub + 6)[0] // 2
            end_start = sub + 14
            begin_start = end_start + 2 * segments + 2
            delta_start = begin_start + 2 * segments
            range_start = delta_start + 2 * segments
            for seg in range(segments):
                end = struct.unpack_from(">H", data, end_start + 2 * seg)[0]
                begin = struct.unpack_from(">H", data, begin_start + 2 * seg)[0]
                delta = struct.unpack_from(">h", data, delta_start + 2 * seg)[0]
                range_position = range_start + 2 * seg
                relative_range = struct.unpack_from(">H", data, range_position)[0]
                for cp in range(begin, min(end, 0xFFFE) + 1):
                    if relative_range:
                        glyph = struct.unpack_from(">H", data, range_position + relative_range + 2 * (cp - begin))[0]
                        glyph = (glyph + delta) % 65536 if glyph else 0
                    else:
                        glyph = (cp + delta) % 65536
                    if glyph:
                        codepoints.add(cp)
        elif fmt == 12:
            groups = struct.unpack_from(">I", data, sub + 12)[0]
            for group in range(groups):
                begin, end, first_glyph = struct.unpack_from(">III", data, sub + 16 + 12 * group)
                for cp in range(begin, end + 1):
                    if first_glyph + cp - begin:
                        codepoints.add(cp)
    return codepoints


def verify(root: Path) -> dict:
    catalog = json.loads((root / "assets/catalog.json").read_text(encoding="utf-8"))
    errors = []
    text_chars = set()
    text_report = []
    font_report = []
    diagnostic = " àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ«»’—–…°0123456789"
    for asset in catalog["assets"]:
        path = Path(asset["path"])
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"Unsafe asset path: {path}")
            continue
        path = root / path
        if sha256(path) != asset["sha256"]:
            errors.append(f"Asset checksum: {asset['id']}")
        rights = asset["rights"]
        if rights["status"] != "verified" or rights["redistribution_allowed"] is not True:
            errors.append(f"Unverified rights: {asset['id']}")
        for evidence in asset["metadata"].get("evidence_files", []):
            evidence_path = Path(evidence["path"])
            if evidence_path.is_absolute() or ".." in evidence_path.parts:
                errors.append(f"Unsafe evidence path: {evidence_path}")
            elif sha256(root / evidence_path) != evidence["sha256"]:
                errors.append(f"Evidence checksum: {evidence_path}")
        if asset["kind"] == "text":
            value = path.read_text(encoding="utf-8")
            if value != unicodedata.normalize("NFC", value):
                errors.append(f"Non-NFC text: {asset['id']}")
            if "\r" in value or "\t" in value or "\ufeff" in value:
                errors.append(f"Unexpected text control: {asset['id']}")
            text_chars.update(ord(c) for c in value if c != "\n")
            text_report.append({"id": asset["id"], "codepoints": len(value), "words": len(value.split())})
    for asset in catalog["assets"]:
        if asset["kind"] != "font":
            continue
        cmap = unicode_cmap((root / asset["path"]).read_bytes())
        missing = "".join(chr(cp) for cp in sorted(text_chars - cmap))
        if missing:
            errors.append(f"Missing text glyphs in {asset['id']}: {missing}")
        font_report.append({
            "id": asset["id"], "glyph_codepoints": len(cmap),
            "missing_demo_characters": missing,
            "missing_french_diagnostic": "".join(c for c in diagnostic if ord(c) not in cmap),
            "long_s": ord("ſ") in cmap,
            "unicode_ligatures_present": "".join(c for c in "ﬀﬁﬂﬃﬄﬅﬆ" if ord(c) in cmap),
        })
    return {
        "schema_version": catalog["schema_version"],
        "catalog_sha256": sha256(root / "assets/catalog.json"),
        "checks": ["asset_sha256", "evidence_sha256", "rights_verified", "text_nfc", "actual_cmap_nonzero_glyphs"],
        "unique_demo_characters": len(text_chars),
        "texts": text_report, "fonts": font_report,
        "errors": errors, "status": "fail" if errors else "pass",
        "limitation": "Cmap coverage does not establish visual legibility or correct shaping; the renderer must verify those.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(Path(__file__).resolve().parents[1])
    result = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.write_text(result, encoding="utf-8")
    print(result, end="")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
