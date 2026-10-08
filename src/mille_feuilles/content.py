"""Explicit, uncalibrated selection of consecutive source body units.

The pure helpers receive text decoded with Python's universal-newline convention.
Only ``preflight_content`` reads files; no function writes a destination or uses
the global random generator. Titles remain independent source documents.
"""

from __future__ import annotations

import hashlib
import io
import random
import re
import unicodedata
from copy import deepcopy
from pathlib import Path

PROFILE = "consecutive-v1"
_INELIGIBLE = "fewer_than_two_body_units"


def _body_identity(asset: dict) -> tuple[str, str, str]:
    if not isinstance(asset, dict):
        raise ValueError("content: source asset must be an object")
    metadata = asset.get("metadata")
    if (asset.get("kind") != "text" or not isinstance(metadata, dict)
            or metadata.get("role") != "body"):
        raise ValueError("content: expected a body text asset")
    identity = asset.get("id")
    document = metadata.get("source_document_id")
    digest = asset.get("sha256")
    if not isinstance(identity, str) or not identity:
        raise ValueError("content: missing asset id")
    if not isinstance(document, str) or not document:
        raise ValueError("content: missing source_document_id")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("content: invalid source SHA-256")
    return identity, document, digest


def index_body_documents(documents: list[tuple[dict, str]]) -> dict:
    """Index body documents and report eligibility, preserving source offsets.

    ``documents`` contains ``(asset, decoded_text)`` pairs. The decoded text must
    already use universal newlines; its offsets are Unicode code points, whereas
    the asset SHA describes the original bytes. This pure helper cannot verify
    that SHA. Source IDs must be distinct; repeated text is intentionally allowed.
    """
    from .catalog import text_units

    if not isinstance(documents, list):
        raise ValueError("content: documents must be a list")
    eligible, records = [], []
    identities, source_documents = set(), set()
    for entry in documents:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise ValueError("content: expected (asset, decoded_text) pairs")
        asset, raw = entry
        identity, document, digest = _body_identity(asset)
        if identity in identities or document in source_documents:
            raise ValueError("content: duplicate asset or source document id")
        identities.add(identity)
        source_documents.add(document)
        if not isinstance(raw, str):
            raise ValueError("content: decoded source must be text")
        if unicodedata.normalize("NFC", raw) != raw:
            raise ValueError(f"content: source is not NFC: {identity}")
        if "\r" in raw:
            raise ValueError(f"content: expected universal-newline decoded text: {identity}")
        units = text_units(raw, "body")
        usable = len(units) >= 2
        records.append({
            "asset_id": identity, "source_document_id": document, "sha256": digest,
            "unit_count": len(units), "eligible": usable,
            "reason": None if usable else _INELIGIBLE,
        })
        if usable:
            eligible.append({"asset": deepcopy(asset), "raw": raw, "units": units})
    if not eligible:
        raise ValueError("content: no body document has at least two units")
    eligible.sort(key=lambda item: item["asset"]["id"])
    records.sort(key=lambda item: item["asset_id"])
    return {
        "documents": eligible,
        "report": {"version": "1", "profile": PROFILE, "calibrated": False,
                   "documents": records},
    }


def choose_body_sequence(index: dict, rng: random.Random) -> dict:
    """Draw document, feasible count, then start, uniformly in that exact order.

    ``index`` is the result of ``index_body_documents``. A count of two remains a
    draw even when three is infeasible. A candidate is never reduced to fit.
    """
    if not isinstance(rng, random.Random) or isinstance(rng, random.SystemRandom):
        raise ValueError("content: rng must be a local deterministic random.Random")
    if not isinstance(index, dict) or not index.get("documents"):
        raise ValueError("content: no indexed body document")
    document = rng.choice(index["documents"])
    units = document["units"]
    count = rng.choice([number for number in (2, 3) if number <= len(units)])
    first = rng.randrange(len(units) - count + 1)
    last = first + count
    start, end = units[first][1], units[last - 1][2]
    return {
        "source": deepcopy(document["asset"]), "text": document["raw"][start:end],
        "start": start, "end": end, "unit_range": [first, last],
    }


def preflight_content(
    source_root: Path, selected_text_assets: list[dict], *, profile: str,
) -> dict:
    """Verify selected body files and return their compact eligibility report.

    Non-body entries are not opened. The caller must supply its partition's
    selected assets and invoke this before creating its output. A successful
    preflight proves textual eligibility, not geometric fit or source rights.
    """
    from .catalog import LIMITS
    from .validation import safe_path

    if profile != PROFILE:
        raise ValueError(f"content: unknown profile: {profile!r}")
    if not isinstance(selected_text_assets, list):
        raise ValueError("content: selected_text_assets must be a list")
    documents, total = [], 0
    for asset in selected_text_assets:
        if not isinstance(asset, dict):
            raise ValueError("content: selected asset must be an object")
        metadata = asset.get("metadata", {})
        if (asset.get("kind") != "text" or not isinstance(metadata, dict)
                or metadata.get("role") != "body"):
            continue
        identity, _, digest = _body_identity(asset)
        relative = asset.get("path")
        if not isinstance(relative, str):
            raise ValueError(f"content: missing source path: {identity}")
        try:
            path = safe_path(Path(source_root), relative)
            with path.open("rb") as stream:
                data = stream.read(LIMITS["document_bytes"] + 1)
            total += len(data)
            if len(data) > LIMITS["document_bytes"] or total > LIMITS["total_text_bytes"]:
                raise ValueError("content: source text byte budget exceeded")
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"content: source SHA-256 mismatch: {identity}")
            # Decode the same verified bytes with Path.read_text's newline rule.
            with io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", newline=None) as stream:
                raw = stream.read()
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"content: unreadable body source: {identity}: {exc}") from exc
        documents.append((asset, raw))
        if len(documents) > LIMITS["documents"]:
            raise ValueError("content: source document count budget exceeded")
    return index_body_documents(documents)["report"]
