"""Verified text catalogs: loading, validation and local multi-document import.

A text asset is one source document. Identifiers are opaque: bundle paths are
derived from hashes, never from document text or identifiers. Nothing is
downloaded; only files named by the import manifest are opened.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path, PurePosixPath

from fontTools.ttLib import TTFont
from jsonschema import Draft202012Validator

from .io import ROOT, sha256, write_json
from .validation import load_json, safe_path

CATALOG_VERSIONS = ("0.2.0", "0.3.0")
IMPORT_VERSION = "0.3.0"
TEXT_ROLES = ("body", "title", "advertisement")
REQUIRED_FONT_FILES = ("OldStandard-Regular.ttf", "OldStandard-Bold.ttf")
NGRAM_FORMAT = "mille-feuilles-ngram-exclusions"
NGRAM_NORMALIZATION = "nfc-casefold-word-v1"
REPORT_FORMAT = "mille-feuilles-import-report"
LIMITS = {
    "manifest_bytes": 16 * 1024 * 1024,
    "documents": 5000,
    "document_bytes": 8 * 1024 * 1024,
    "total_text_bytes": 256 * 1024 * 1024,
    "evidence_bytes": 16 * 1024 * 1024,
    "identifier_chars": 256,
    "document_exclusion_bytes": 64 * 1024 * 1024,
    "ngram_exclusion_bytes": 256 * 1024 * 1024,
}
_ROW_FIELDS = {
    "path", "role", "source_document_id", "source_group_id", "language", "date",
    "source_uri", "content_type", "historical_corpus", "rights",
}
_ROW_REQUIRED = {
    "path", "role", "source_document_id", "source_group_id", "language", "source_uri", "rights",
}
_RIGHTS_FIELDS = {"status", "license", "evidence_path", "attribution", "redistribution_allowed"}
_EVIDENCE_SUFFIXES = {".txt", ".md", ".html", ".htm", ".pdf", ".json", ".xml"}
_UNIT_PATTERNS = {
    "body": r"\S[^\n]*(?:\n(?!\n)[^\n]+)*",
    "advertisement": r"\S[^\n]*(?:\n(?!\n)[^\n]+)*",
    "title": r"[^\n]+",
}
_DATE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")


class CatalogError(ValueError):
    """A catalog or import input that cannot be used safely."""


def _digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def text_units(text: str, role: str) -> list[tuple[str, int, int]]:
    """Selectable units with code-point offsets in the raw source text."""
    if role not in _UNIT_PATTERNS:
        raise CatalogError(f"Rôle de texte inconnu : {role!r}")
    units = []
    for match in re.finditer(_UNIT_PATTERNS[role], text):
        value = match.group().strip()
        if value:
            units.append((value, match.start(), match.end()))
    return units


def normalize_unit(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def text_group(asset: dict) -> str:
    metadata = asset.get("metadata", {})
    return metadata.get("source_group_id") or metadata["source_document_id"]


def ngram_digests(text: str, n: int, salt: bytes) -> set[str]:
    """Salted 128-bit digests of word n-grams (normalization nfc-casefold-word-v1)."""
    words = re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold())
    return {
        hashlib.sha256(salt + b"\x1f" + " ".join(words[i:i + n]).encode()).hexdigest()[:32]
        for i in range(len(words) - n + 1)
    }


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    candidates = [
        Path(__file__).parent / "schemas" / "assets.schema.json",
        ROOT / "schemas" / "assets.schema.json",
    ]
    path = next((p for p in candidates if p.is_file()), candidates[-1])
    schema = load_json(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def load_catalog(bundle_root: Path) -> dict:
    """Strict JSON plus schema; raises CatalogError."""
    try:
        catalog = load_json(safe_path(Path(bundle_root), "assets/catalog.json"))
    except (OSError, ValueError) as exc:
        raise CatalogError(f"Catalogue illisible : {exc}") from exc
    errors = sorted(_validator().iter_errors(catalog), key=lambda e: list(map(str, e.path)))
    if errors:
        where = ".".join(map(str, errors[0].path)) or "$"
        raise CatalogError(f"Catalogue invalide ({where}) : {errors[0].message}")
    return catalog


def _text_problems(value: str) -> list[str]:
    problems = []
    if value.startswith("﻿"):
        problems.append("BOM UTF-8 interdit")
    if unicodedata.normalize("NFC", value) != value:
        problems.append("texte non NFC")
    controls = sorted({c for c in value if c != "\n" and unicodedata.category(c) in {"Cc", "Cf", "Cs"}})
    if controls:
        problems.append("caractères de contrôle ou de format : " + " ".join(f"U+{ord(c):04X}" for c in controls))
    return problems


def _font_cmaps(bundle_root: Path, catalog: dict) -> tuple[dict[str, set[int]], list[str]]:
    by_name = {}
    for asset in catalog["assets"]:
        if asset["kind"] == "font":
            by_name.setdefault(PurePosixPath(asset["path"]).name, []).append(asset)
    cmaps, errors = {}, []
    for name in REQUIRED_FONT_FILES:
        fonts = by_name.get(name, [])
        if len(fonts) != 1:
            errors.append(f"fonte requise absente ou ambiguë : {name}")
            continue
        try:
            with TTFont(safe_path(bundle_root, fonts[0]["path"])) as font:
                cmap = font.getBestCmap() or {}
                cmaps[name] = {cp for cp, glyph in cmap.items() if font.getGlyphID(glyph) != 0}
        except Exception as exc:  # noqa: BLE001 - any font parsing failure is a catalog error
            errors.append(f"fonte illisible {name} : {exc}")
    return cmaps, errors


def _missing_glyphs(value: str, cmaps: dict[str, set[int]]) -> list[str]:
    chars = {ord(c) for c in value if c not in "\n"}
    return [
        f"glyphes absents dans {name} : {''.join(chr(cp) for cp in sorted(chars - cmap))!r}"
        for name, cmap in sorted(cmaps.items())
        if chars - cmap
    ]


def validate_catalog(bundle_root: Path, catalog: dict | None = None) -> list[str]:
    """Return every problem preventing composition from this bundle."""
    bundle_root = Path(bundle_root)
    if catalog is None:
        try:
            catalog = load_catalog(bundle_root)
        except CatalogError as exc:
            return [str(exc)]
    else:
        errors = list(_validator().iter_errors(catalog))
        if errors:
            return [f"catalogue invalide : {errors[0].message}"]
    errors = []
    version = catalog["schema_version"]
    seen = {"id": {}, "sha256": {}, "source_document_id": {}}
    for asset in catalog["assets"]:
        for key, value in (("id", asset["id"]), ("sha256", asset["sha256"])):
            seen[key].setdefault(value, []).append(asset["id"])
        if asset["kind"] == "text":
            seen["source_document_id"].setdefault(
                asset["metadata"].get("source_document_id"), []
            ).append(asset["id"])
    for key, values in seen.items():
        for value, owners in sorted(values.items(), key=lambda kv: str(kv[0])):
            if len(owners) > 1:
                errors.append(f"{key} dupliqué ({value}) : {', '.join(owners)}")
    cmaps, font_errors = _font_cmaps(bundle_root, catalog)
    errors += font_errors
    roles = {role: 0 for role in TEXT_ROLES}
    for asset in catalog["assets"]:
        label = asset["id"]
        try:
            path = safe_path(bundle_root, asset["path"])
            if not path.is_file() or sha256(path) != asset["sha256"]:
                errors.append(f"{label} : fichier absent ou empreinte différente")
                continue
        except (OSError, ValueError) as exc:
            errors.append(f"{label} : chemin refusé ({exc})")
            continue
        rights = asset["rights"]
        if rights["status"] != "verified" or rights["redistribution_allowed"] is not True:
            errors.append(f"{label} : droits non vérifiés ou redistribution interdite")
        evidence = asset["metadata"].get("evidence_files", [])
        if not isinstance(evidence, list):
            errors.append(f"{label} : evidence_files doit être une liste")
            evidence = []
        if version == "0.3.0" and not evidence:
            errors.append(f"{label} : au moins une preuve locale hachée est requise en 0.3.0")
        records = []
        for record in evidence:
            if (
                not isinstance(record, dict)
                or not isinstance(record.get("path"), str)
                or not isinstance(record.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
            ):
                errors.append(f"{label} : preuve mal formée (path et sha256 requis)")
                continue
            records.append(record)
        local_uri = "://" not in rights["evidence_uri"]
        if local_uri and not any(r["path"] == rights["evidence_uri"] for r in records):
            if version == "0.3.0":
                errors.append(f"{label} : evidence_uri local absent des preuves hachées")
            else:
                # 0.2.0 compatibility: a shared local notice may be declared only here.
                records.append({"path": rights["evidence_uri"], "sha256": None})
        for record in records:
            try:
                proof = safe_path(bundle_root, record["path"])
                if not proof.is_file():
                    errors.append(f"{label} : preuve absente {record['path']}")
                elif record["sha256"] is not None and sha256(proof) != record["sha256"]:
                    errors.append(f"{label} : empreinte de preuve différente {record['path']}")
            except (OSError, ValueError) as exc:
                errors.append(f"{label} : chemin de preuve refusé ({exc})")
        if asset["kind"] != "text":
            continue
        metadata = asset["metadata"]
        role = metadata.get("role")
        if role not in TEXT_ROLES:
            errors.append(f"{label} : rôle de texte absent ou inconnu")
            continue
        if not metadata.get("source_document_id"):
            errors.append(f"{label} : source_document_id absent")
        if version == "0.3.0" and not metadata.get("source_group_id"):
            errors.append(f"{label} : source_group_id absent")
        try:
            value = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{label} : UTF-8 invalide")
            continue
        errors += [f"{label} : {p}" for p in _text_problems(value)]
        if not text_units(value, role):
            errors.append(f"{label} : aucune unité de texte")
        errors += [f"{label} : {p}" for p in _missing_glyphs(value, cmaps)]
        roles[role] += 1
    errors += [f"aucun texte de rôle {role}" for role, count in roles.items() if not count]
    return errors


def text_assets_by_role(catalog: dict, allowed: set[str] | None = None) -> dict[str, list[dict]]:
    result = {role: [] for role in TEXT_ROLES}
    for asset in sorted(catalog["assets"], key=lambda a: a["id"]):
        if asset["kind"] == "text" and (allowed is None or asset["id"] in allowed):
            role = asset["metadata"].get("role")
            if role in result:
                result[role].append(asset)
    return result


def _identifier(value) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > LIMITS["identifier_chars"]
        or any(unicodedata.category(c)[0] in "CZ" and c != " " for c in value)
        or unicodedata.normalize("NFC", value) != value
    ):
        return None
    return value


def _input_file(base: Path, relative, limit: int) -> Path:
    if not isinstance(relative, str):
        raise CatalogError("chemin absent")
    path = safe_path(base, relative)
    if not path.is_file():
        raise CatalogError(f"fichier absent : {relative}")
    if path.stat().st_size > limit:
        raise CatalogError(f"fichier trop volumineux : {relative}")
    return path


def _load_document_exclusions(path: Path) -> set[str]:
    if path.stat().st_size > LIMITS["document_exclusion_bytes"]:
        raise CatalogError("liste d'exclusion de documents trop volumineuse")
    try:
        lines = path.read_bytes().decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise CatalogError("liste d'exclusion de documents : UTF-8 invalide") from exc
    keys = set()
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key = _identifier(line)
        if key is None:
            raise CatalogError(f"liste d'exclusion de documents : clé invalide ligne {number}")
        keys.add(key)
    return keys


def _load_ngram_exclusions(path: Path) -> dict:
    if path.stat().st_size > LIMITS["ngram_exclusion_bytes"]:
        raise CatalogError("fichier d'exclusion de n-grammes trop volumineux")
    try:
        data = load_json(path)
    except (OSError, ValueError) as exc:
        raise CatalogError(f"exclusions de n-grammes illisibles : {exc}") from exc
    expected = {"format", "version", "n", "normalization", "salt_hex", "digest", "hashes"}
    if not isinstance(data, dict) or set(data) != expected:
        raise CatalogError("exclusions de n-grammes : champs attendus " + ", ".join(sorted(expected)))
    if (data["format"], data["version"], data["normalization"], data["digest"]) != (
        NGRAM_FORMAT, "1", NGRAM_NORMALIZATION, "sha256-128"
    ):
        raise CatalogError("exclusions de n-grammes : format, version, normalisation ou digest non pris en charge")
    if type(data["n"]) is not int or not 3 <= data["n"] <= 32:
        raise CatalogError("exclusions de n-grammes : n hors de 3..32")
    salt = data["salt_hex"]
    if not isinstance(salt, str) or re.fullmatch(r"(?:[0-9a-f]{2}){16,64}", salt) is None:
        raise CatalogError("exclusions de n-grammes : salt_hex doit compter 16 à 64 octets hexadécimaux")
    hashes = data["hashes"]
    if not isinstance(hashes, list) or any(
        not isinstance(h, str) or re.fullmatch(r"[0-9a-f]{32}", h) is None for h in hashes
    ):
        raise CatalogError("exclusions de n-grammes : empreintes de 32 caractères hexadécimaux attendues")
    if hashes != sorted(set(hashes)):
        raise CatalogError("exclusions de n-grammes : empreintes non triées ou dupliquées")
    return {"n": data["n"], "salt": bytes.fromhex(salt), "hashes": set(hashes)}


def _builtin_fonts() -> list[dict]:
    """Verified embedded fonts (catalog entries); texts are never selected."""
    fonts = [asset for asset in load_catalog(ROOT)["assets"] if asset["kind"] == "font"]
    for asset in fonts:
        for record in [{"path": asset["path"], "sha256": asset["sha256"]}] + asset["metadata"].get(
            "evidence_files", []
        ):
            if sha256(safe_path(ROOT, record["path"])) != record["sha256"]:
                raise CatalogError(f"Fonte embarquée altérée : {record['path']}")
    return fonts


def _copy_fonts(fonts: list[dict], bundle_root: Path) -> None:
    for asset in fonts:
        for record in [{"path": asset["path"]}] + asset["metadata"].get("evidence_files", []):
            dst = safe_path(bundle_root, record["path"])
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(safe_path(ROOT, record["path"]).read_bytes())


def _parse_manifest(manifest_path: Path) -> list[tuple[int, dict | None, list[str]]]:
    if manifest_path.stat().st_size > LIMITS["manifest_bytes"]:
        raise CatalogError("manifeste d'import trop volumineux")
    try:
        lines = manifest_path.read_bytes().decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise CatalogError("manifeste d'import : UTF-8 invalide") from exc
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if len(rows) >= LIMITS["documents"]:
            raise CatalogError(f"plus de {LIMITS['documents']} documents dans le manifeste")
        try:
            row = json.loads(line, object_pairs_hook=_unique_pairs, parse_constant=_no_constant)
        except ValueError as exc:
            rows.append((number, None, [f"JSON invalide : {exc}"]))
            continue
        problems = []
        if not isinstance(row, dict):
            rows.append((number, None, ["ligne JSON non objet"]))
            continue
        if set(row) - _ROW_FIELDS:
            problems.append("champs inconnus : " + ", ".join(sorted(set(row) - _ROW_FIELDS)))
        if _ROW_REQUIRED - set(row):
            problems.append("champs manquants : " + ", ".join(sorted(_ROW_REQUIRED - set(row))))
        for key in ("source_document_id", "source_group_id", "source_uri"):
            if key in row and _identifier(row[key]) is None:
                problems.append(f"{key} invalide")
        if row.get("role") not in TEXT_ROLES:
            problems.append("rôle inconnu")
        if row.get("language") != "fr":
            problems.append("langue non prise en charge par ce profil (fr)")
        if "date" in row and (not isinstance(row["date"], str) or not _DATE.fullmatch(row["date"])):
            problems.append("date ISO invalide")
        if "historical_corpus" in row and not isinstance(row["historical_corpus"], bool):
            problems.append("historical_corpus doit être booléen")
        if "content_type" in row and _identifier(row["content_type"]) is None:
            problems.append("content_type invalide")
        rights = row.get("rights")
        if not isinstance(rights, dict) or set(rights) != _RIGHTS_FIELDS:
            problems.append("rights doit contenir exactement " + ", ".join(sorted(_RIGHTS_FIELDS)))
        else:
            if rights["status"] != "verified" or rights["redistribution_allowed"] is not True:
                problems.append("droits non vérifiés ou redistribution interdite")
            for key in ("license", "attribution"):
                if not isinstance(rights[key], str) or not rights[key].strip():
                    problems.append(f"rights.{key} vide")
        rows.append((number, row, problems))
    return rows


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"clé JSON dupliquée : {key}")
        result[key] = value
    return result


def _no_constant(value):
    raise ValueError(f"nombre JSON non fini : {value}")


def import_texts(manifest_path: Path, bundle_root: Path, exclusions: dict | None = None) -> dict:
    """Build a self-contained 0.3.0 bundle from a local JSONL import manifest."""
    manifest_path = Path(manifest_path).absolute()
    bundle_root = Path(bundle_root).absolute()
    if bundle_root.exists() and (not bundle_root.is_dir() or any(bundle_root.iterdir())):
        raise CatalogError(f"Bundle non vide, aucune écriture : {bundle_root}")
    if not manifest_path.is_file():
        raise CatalogError(f"Manifeste d'import absent : {manifest_path}")
    exclusions = dict(exclusions or {})
    if set(exclusions) - {"documents", "ngrams"}:
        raise CatalogError("exclusions : seules les clés documents et ngrams sont admises")
    # Read every control input before the first write.
    excluded_keys, ngrams, exclusion_report = set(), None, {}
    documents_path = exclusions.get("documents")
    if documents_path is not None:
        documents_path = Path(documents_path)
        excluded_keys = _load_document_exclusions(documents_path)
        exclusion_report["documents"] = {
            "status": "evaluated", "sha256": sha256(documents_path), "entries": len(excluded_keys),
        }
    else:
        exclusion_report["documents"] = {"status": "not_evaluated"}
    ngrams_path = exclusions.get("ngrams")
    if ngrams_path is not None:
        ngrams_path = Path(ngrams_path)
        ngrams = _load_ngram_exclusions(ngrams_path)
        exclusion_report["ngrams"] = {
            "status": "evaluated", "sha256": sha256(ngrams_path), "n": ngrams["n"],
            "normalization": NGRAM_NORMALIZATION, "hashes": len(ngrams["hashes"]),
        }
    else:
        exclusion_report["ngrams"] = {"status": "not_evaluated"}
    rows = _parse_manifest(manifest_path)
    base = manifest_path.parent

    fonts = _builtin_fonts()
    cmaps, font_errors = _font_cmaps(ROOT, {"assets": fonts})
    if font_errors:
        raise CatalogError("; ".join(font_errors))

    entries, total = [], 0
    for number, row, problems in rows:
        problems = list(problems)
        content = evidence = None
        if isinstance(row, dict) and "path" in row:
            # Read even when the row has other problems: content duplicates
            # must count every occurrence. Nothing read here is catalogued.
            try:
                path = _input_file(base, row["path"], LIMITS["document_bytes"])
                content = path.read_bytes()
            except (OSError, ValueError) as exc:
                problems.append(str(exc))
            else:
                total += len(content)
                if total > LIMITS["total_text_bytes"]:
                    raise CatalogError("volume total de texte au-delà de la limite d'import")
        if content is not None and not problems:
            try:
                proof = _input_file(base, row["rights"]["evidence_path"], LIMITS["evidence_bytes"])
                evidence = (proof, proof.read_bytes())
                if not evidence[1].strip():
                    problems.append("preuve de droits vide")
            except (OSError, ValueError) as exc:
                problems.append(str(exc))
        if content is not None and not problems:
            try:
                value = content.decode("utf-8")
            except UnicodeDecodeError:
                problems.append("UTF-8 invalide")
            else:
                problems += _text_problems(value)
                if "\r" in value or "\t" in value:
                    problems.append("retour chariot ou tabulation interdits")
                if not text_units(value, row["role"]):
                    problems.append("aucune unité de texte")
                problems += _missing_glyphs(value, cmaps)
                keys = {row["source_document_id"], row["source_group_id"], row["source_uri"]}
                if keys & excluded_keys:
                    problems.append("document exclu par la liste de documents protégés")
                if ngrams and ngram_digests(value, ngrams["n"], ngrams["salt"]) & ngrams["hashes"]:
                    problems.append("document exclu : n-gramme protégé")
        entries.append((number, row, problems, content, evidence))
    # Duplicates are ambiguous: every occurrence of a repeated identifier or
    # content is rejected, counted over all rows (accepted or not), so that the
    # result does not depend on which check runs first or on the line order.
    def doc_id(row):
        value = row.get("source_document_id") if isinstance(row, dict) else None
        return value if isinstance(value, str) else None

    id_counts, sha_counts = {}, {}
    for _, row, _, content, _ in entries:
        if doc_id(row) is not None:
            id_counts[doc_id(row)] = id_counts.get(doc_id(row), 0) + 1
        if content is not None:
            sha_counts[_digest(content)] = sha_counts.get(_digest(content), 0) + 1
    candidates, rejected = [], []
    for number, row, problems, content, evidence in entries:
        if doc_id(row) is not None and id_counts[doc_id(row)] > 1:
            problems.append("source_document_id dupliqué dans le manifeste")
        if content is not None and sha_counts[_digest(content)] > 1:
            problems.append("sha256 dupliqué dans le manifeste")
        if problems:
            rejected.append({"line": number, "source_document_id": doc_id(row), "reasons": problems})
        else:
            candidates.append((number, row, content, evidence, _digest(content)))

    # First write: only after every input has been read and checked.
    bundle_root.mkdir(parents=True, exist_ok=True)
    _copy_fonts(fonts, bundle_root)
    assets, accepted = [], []
    for number, row, content, (proof, proof_bytes), digest in sorted(
        candidates, key=lambda item: item[1]["source_document_id"]
    ):
        relative = f"assets/texts/imported/{digest[:20]}.txt"
        suffix = proof.suffix.lower() if proof.suffix.lower() in _EVIDENCE_SUFFIXES else ".bin"
        proof_digest = _digest(proof_bytes)
        proof_relative = f"assets/evidence/{proof_digest[:20]}{suffix}"
        for rel, data in ((relative, content), (proof_relative, proof_bytes)):
            target = safe_path(bundle_root, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        value = content.decode("utf-8")
        metadata = {
            "role": row["role"],
            "source_document_id": row["source_document_id"],
            "source_group_id": row["source_group_id"],
            "language": row["language"],
            "units": len(text_units(value, row["role"])),
            "unit_separator": "\\n" if row["role"] == "title" else "\\n\\n",
            "preparation": "Import local Mille Feuilles 0.3.0 : octets source conservés, UTF-8 NFC vérifié.",
            "evidence_files": [{"path": proof_relative, "sha256": proof_digest}],
        }
        for key in ("date", "content_type", "historical_corpus"):
            if key in row:
                metadata[key] = row[key]
        asset_id = "text_" + _digest(row["source_document_id"])[:20]
        assets.append({
            "id": asset_id,
            "kind": "text",
            "path": relative,
            "sha256": digest,
            "source_uri": row["source_uri"],
            "rights": {
                "status": "verified",
                "license": row["rights"]["license"],
                "evidence_uri": proof_relative,
                "attribution": row["rights"]["attribution"],
                "redistribution_allowed": True,
            },
            "metadata": metadata,
        })
        accepted.append({
            "asset_id": asset_id, "source_document_id": row["source_document_id"],
            "source_group_id": row["source_group_id"], "role": row["role"], "sha256": digest,
        })
    roles = {asset["metadata"]["role"] for asset in assets}
    missing_roles = [role for role in TEXT_ROLES if role not in roles]
    status = "fail" if missing_roles else "pass"
    catalog = {"schema_version": IMPORT_VERSION, "assets": fonts + assets}
    catalog_errors = []
    if status == "pass":
        write_json(bundle_root / "assets/catalog.json", catalog)
        catalog_errors = validate_catalog(bundle_root)
        if catalog_errors:
            status = "fail"
            (bundle_root / "assets/catalog.json").unlink()
    external = all(v["status"] == "evaluated" for v in exclusion_report.values())
    report = {
        "format": REPORT_FORMAT,
        "version": "1",
        "status": status,
        "manifest_sha256": sha256(manifest_path),
        "accepted": accepted,
        "rejected": sorted(rejected, key=lambda r: (r["line"], r["reasons"])),
        "missing_roles": missing_roles,
        "catalog_errors": catalog_errors,
        "exclusions": exclusion_report,
        "external_protection": "evaluated" if external else "NOT EVALUATED",
        "external_protection_note": (
            "Protection contre les fuites évaluée seulement pour les listes fournies."
            if external else
            "Aucune affirmation d'absence de fuite vers des jeux de test externes."
        ),
        "limits": LIMITS,
    }
    write_json(bundle_root / "assets/import-report.json", report)
    return report
