"""Strict, read-only validation of canonical 0.2.0 and 0.3.0 datasets.

Only files named by the dataset are opened, after containment checks. The
historical paths inside the calibration audit are evidence, never inputs.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import unicodedata
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator
from PIL import Image, ImageDraw, ImageFilter
from shapely.geometry import LineString, Polygon, box
from shapely.affinity import affine_transform

SCHEMA_VERSION = "0.2.0"
MEASURED_PROFILE = "fr_press_19c_columns_4_6_measured"
LAYOUT_PROFILE = "fr_press_19c_layout_v2"
MEASURED_PROFILES = {MEASURED_PROFILE, LAYOUT_PROFILE}
TOLERANCE = 0.5
_NON_TEXT = {"illustration", "separateur"}
_LEGIBILITY = {"readable": 0, "uncertain": 1, "illegible": 2}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


def load_json(path: Path):
    """Read UTF-8 JSON while rejecting repeated keys and nonstandard numbers."""
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    errors = list(_finite_errors(value))
    if errors:
        raise ValueError(errors[0])
    return value


def _finite_errors(value, path="$"):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            yield f"{path}: non-finite number"
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _finite_errors(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for i, child in enumerate(value):
            yield from _finite_errors(child, f"{path}[{i}]")


@lru_cache(maxsize=3)
def _schema(name):
    # Wheels install schemas alongside the package; source checkouts use /schemas.
    candidates = [
        Path(__file__).parent / "schemas" / f"{name}.schema.json",
        Path(__file__).resolve().parents[2] / "schemas" / f"{name}.schema.json",
    ]
    path = next((p for p in candidates if p.is_file()), candidates[0])
    schema = load_json(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _structural_errors(value, name):
    errors = list(_finite_errors(value))
    for issue in sorted(_schema(name).iter_errors(value), key=lambda e: str(list(e.path))):
        path = ".".join(map(str, issue.path)) or "$"
        errors.append(f"{name}.{path}: {issue.message}")
    return errors


def safe_path(root: Path, relative: str) -> Path:
    """Resolve a portable relative file path without escaping the dataset root."""
    if not isinstance(relative, str) or not relative or "\\" in relative or "\0" in relative:
        raise ValueError(f"unsafe relative path: {relative!r}")
    parts = relative.split("/")
    if PurePosixPath(relative).is_absolute() or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"unsafe relative path: {relative!r}")
    if ":" in parts[0]:
        raise ValueError(f"unsafe relative path: {relative!r}")
    try:
        resolved = (root / relative).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"cannot resolve safe dataset path: {relative!r}: {exc}") from exc
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes dataset root: {relative!r}")
    return resolved


def _polygon(points, label, width, height, errors):
    if points[0] == points[-1]:
        errors.append(f"{label}: repeated closing polygon vertex")
    if len({tuple(p) for p in points}) != len(points):
        errors.append(f"{label}: polygon vertices must be distinct")
    if any(not (0 <= x <= width and 0 <= y <= height) for x, y in points):
        errors.append(f"{label}: polygon outside final image")
    signed_twice_area = sum(
        x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1])
    )
    if not math.isfinite(signed_twice_area) or signed_twice_area <= 0:
        errors.append(f"{label}: polygon must have positive signed area (clockwise on screen)")
    poly = Polygon(points)
    if not poly.is_valid or not math.isfinite(poly.area) or poly.area <= 0:
        errors.append(f"{label}: polygon must be simple with positive area")
        return None
    return poly


def validate_page(page: dict) -> list[str]:
    """Return structural and semantic errors, without consulting external files."""
    errors = _structural_errors(page, "page")
    if errors:
        return errors
    width, height = page["image"]["width"], page["image"]["height"]
    arrays = {name: page[name] for name in ("articles", "blocks", "lines", "words")}
    all_ids = [page["page_id"]] + [item["id"] for items in arrays.values() for item in items]
    for identity, count in Counter(all_ids).items():
        if count > 1:
            errors.append(f"duplicate id across page entities: {identity}")
    articles, blocks, lines, words = (
        {x["id"]: x for x in arrays[name]} for name in ("articles", "blocks", "lines", "words")
    )
    polygons = {}
    for items in (blocks, lines, words):
        for identity, item in items.items():
            polygons[identity] = _polygon(item["polygon"], identity, width, height, errors)
    block_owners, line_owners, word_owners = Counter(), Counter(), Counter()
    for article in articles.values():
        for bid in article["block_ids"]:
            block_owners[bid] += 1
            if bid not in blocks or blocks[bid]["article_id"] != article["id"]:
                errors.append(f"{article['id']}: invalid/non-reciprocal block reference {bid}")
    for block in blocks.values():
        aid, bid = block["article_id"], block["id"]
        if aid is not None and (aid not in articles or bid not in articles[aid]["block_ids"]):
            errors.append(f"{bid}: invalid/non-reciprocal article reference {aid}")
        if block_owners[bid] != (1 if aid is not None else 0):
            errors.append(f"{bid}: invalid article ownership")
        if block["category"] == "separateur" and aid is not None:
            errors.append(f"{bid}: separator must be outside articles")
        if block["category"] == "annonce":
            if aid is None:
                errors.append(f"{bid}: advertisement requires its own article")
            elif aid in articles and any(
                blocks[x]["category"] != "annonce"
                for x in articles[aid]["block_ids"]
                if x in blocks
            ):
                errors.append(f"{bid}: advertisement article contains unrelated categories")
        if block["category"] in _NON_TEXT and block["line_ids"]:
            errors.append(f"{bid}: nontextual block contains lines")
        if block["category"] not in _NON_TEXT and not block["line_ids"]:
            errors.append(f"{bid}: textual block must contain lines")
        for lid in block["line_ids"]:
            line_owners[lid] += 1
            if lid not in lines or lines[lid]["block_id"] != bid:
                errors.append(f"{bid}: invalid/non-reciprocal line reference {lid}")
    for line in lines.values():
        lid, bid = line["id"], line["block_id"]
        if line_owners[lid] != 1 or bid not in blocks or lid not in blocks[bid]["line_ids"]:
            errors.append(f"{lid}: invalid line ownership")
        if polygons.get(lid) is not None and polygons.get(bid) is not None:
            if not polygons[bid].buffer(TOLERANCE).covers(polygons[lid]):
                errors.append(f"{lid}: line outside block")
        baseline = LineString(line["baseline"])
        if not baseline.is_simple or baseline.length == 0:
            errors.append(f"{lid}: baseline must be a non-degenerate simple polyline")
        if polygons.get(lid) is not None and not polygons[lid].buffer(TOLERANCE).covers(baseline):
            errors.append(f"{lid}: baseline outside line envelope")
        if any(not (0 <= x <= width and 0 <= y <= height) for x, y in line["baseline"]):
            errors.append(f"{lid}: baseline outside final image")
        if any(q[0] <= p[0] for p, q in zip(line["baseline"], line["baseline"][1:])):
            errors.append(f"{lid}: baseline must follow left-to-right reading direction")
        text = line["text"]
        if unicodedata.normalize("NFC", text) != text:
            errors.append(f"{lid}: text is not NFC")
        if text != text.strip(" ") or any(c.isspace() and c != " " for c in text):
            errors.append(f"{lid}: invalid line whitespace")
        if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in text):
            errors.append(f"{lid}: invisible control/format character in composed text")
        previous_end, worst = 0, 0
        for wid in line["word_ids"]:
            word_owners[wid] += 1
            if wid not in words or words[wid]["line_id"] != lid:
                errors.append(f"{lid}: invalid/non-reciprocal word reference {wid}")
                continue
            word = words[wid]
            start, end = word["char_span"]
            if not (previous_end <= start < end <= len(text)):
                errors.append(f"{wid}: overlapping, unordered or invalid Unicode span")
            elif any(c != " " for c in text[previous_end:start]):
                errors.append(f"{wid}: uncovered non-space characters before word")
            if text[start:end] != word["text"]:
                errors.append(f"{wid}: Unicode span differs from word text")
            previous_end = max(previous_end, end)
            worst = max(worst, _LEGIBILITY[word["legibility"]])
        if any(c != " " for c in text[previous_end:]):
            errors.append(f"{lid}: uncovered trailing non-space characters")
        if _LEGIBILITY[line["legibility"]] != worst:
            errors.append(f"{lid}: line legibility is not worst word legibility")
    groups = defaultdict(list)
    for word in words.values():
        wid, lid = word["id"], word["line_id"]
        if word_owners[wid] != 1 or lid not in lines or wid not in lines[lid]["word_ids"]:
            errors.append(f"{wid}: invalid word ownership")
        if (
            any(c.isspace() for c in word["text"])
            or unicodedata.normalize("NFC", word["text"]) != word["text"]
        ):
            errors.append(f"{wid}: word must be NFC and contain no whitespace")
        if polygons.get(wid) is not None and polygons.get(lid) is not None:
            if not polygons[lid].buffer(TOLERANCE).covers(polygons[wid]):
                errors.append(f"{wid}: word outside line")
        if word["hyphenation"] is not None:
            groups[word["hyphenation"]["group_id"]].append(word)
    order = page["reading_order"]
    textual = {bid for bid, b in blocks.items() if b["category"] not in _NON_TEXT}
    nontextual = set(blocks) - textual
    if set(order["block_ids"]) != textual:
        errors.append("reading_order.block_ids must be exactly the textual blocks")
    if set(order["unordered_block_ids"]) != nontextual:
        errors.append("reading_order.unordered_block_ids must be exactly the nontextual blocks")
    expected_lines = [
        lid for bid in order["block_ids"] if bid in blocks for lid in blocks[bid]["line_ids"]
    ]
    if order["line_ids"] != expected_lines or set(order["line_ids"]) != set(lines):
        errors.append(
            "reading_order.line_ids must concatenate all ordered block lines exactly once"
        )
    for article in articles.values():
        expected = [bid for bid in article["block_ids"] if bid in textual]
        actual = [
            bid
            for bid in order["block_ids"]
            if bid in blocks and blocks[bid]["article_id"] == article["id"]
        ]
        positions = [i for i, bid in enumerate(order["block_ids"]) if bid in actual]
        if actual != expected or (positions and positions[-1] - positions[0] + 1 != len(positions)):
            errors.append(f"{article['id']}: article blocks must be consecutive in article order")
    line_positions = {lid: i for i, lid in enumerate(order["line_ids"])}
    for gid, members in groups.items():
        starts = [w for w in members if w["hyphenation"]["part"] == "start"]
        ends = [w for w in members if w["hyphenation"]["part"] == "end"]
        if len(starts) != 1 or len(ends) != 1:
            errors.append(f"{gid}: hyphenation needs exactly one start and one end")
            continue
        start, end = starts[0], ends[0]
        sl, el = lines.get(start["line_id"]), lines.get(end["line_id"])
        if not sl or not el:
            continue
        sb, eb = blocks.get(sl["block_id"]), blocks.get(el["block_id"])
        if (
            not sb
            or not eb
            or sb["article_id"] is None
            or sb["article_id"] != eb["article_id"]
            or line_positions.get(el["id"], -2) != line_positions.get(sl["id"], -2) + 1
        ):
            errors.append(f"{gid}: hyphenation must join consecutive lines of the same article")
        if sl["word_ids"][-1] != start["id"] or el["word_ids"][0] != end["id"]:
            errors.append(f"{gid}: hyphenation must join last/first words of consecutive lines")
        reconstructed = start["text"][:-1] + end["text"]
        if not start["text"].endswith("-") or any(
            w["hyphenation"]["reconstructed_text"] != reconstructed for w in members
        ):
            errors.append(f"{gid}: invalid visible hyphen or reconstructed text")
    for span in page["provenance"]["text_spans"]:
        if span["start"] >= span["end"] or span["asset_id"] not in page["provenance"]["asset_ids"]:
            errors.append("provenance: empty/reversed text span or undeclared asset")
    if page["schema_version"] == "0.3.0":
        errors.extend(_validate_span_bindings(page))
    for transform in page["transforms"]:
        if transform["geometry"] != "identity":
            matrix = transform["geometry"]["matrix"]
            determinant = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
            if matrix[2] != [0, 0, 1] or not math.isfinite(determinant) or abs(determinant) < 1e-12:
                errors.append("transforms: geometry must be a non-singular affine matrix")
    if page["profile"] == LAYOUT_PROFILE and not errors:
        errors.extend(_layout_page_errors(page))
    return errors


def _validate_span_bindings(page: dict) -> list[str]:
    """Validate complete, disjoint ownership of textual blocks in version 0.3."""
    errors = []
    articles = {a["id"]: a for a in page["articles"]}
    blocks = {b["id"]: b for b in page["blocks"]}
    lines = {line["id"]: line for line in page["lines"]}
    owners = defaultdict(list)
    template_ids = page["provenance"].get("extensions", {}).get("mf:template_article_ids", [])
    article_order = list(dict.fromkeys(
        blocks[bid]["article_id"]
        for bid in page["reading_order"]["block_ids"] if bid in blocks
    ))
    if template_ids != [aid for aid in article_order if aid in template_ids]:
        errors.append("provenance: template article ids must exist in reading order")
    for aid in template_ids:
        if aid not in articles:
            errors.append(f"provenance: unknown template article {aid}")
            continue
        for bid in articles[aid]["block_ids"]:
            if bid in blocks and blocks[bid]["category"] not in _NON_TEXT:
                owners[bid].append("template")
    for index, span in enumerate(page["provenance"]["text_spans"]):
        aid = span["article_id"]
        bids = span["block_ids"]
        label = f"text span {index}"
        if aid not in articles:
            errors.append(f"{label}: unknown article_id {aid}")
        else:
            expected = [bid for bid in articles[aid]["block_ids"] if bid in bids]
            if bids != expected:
                errors.append(f"{label}: block_ids must follow their article order")
        for bid in bids:
            block = blocks.get(bid)
            if block is None or block["category"] in _NON_TEXT:
                errors.append(f"{label}: unknown or nontextual block {bid}")
                continue
            if block["article_id"] != aid:
                errors.append(f"{label}: non-reciprocal article/block binding {bid}")
            owners[bid].append(index)
    for bid, block in blocks.items():
        if block["category"] not in _NON_TEXT and len(owners[bid]) != 1:
            errors.append(f"{bid}: textual block must have exactly one provenance owner")
    hyphen_owners = defaultdict(list)
    for word in page["words"]:
        if word["hyphenation"] is not None and word["line_id"] in lines:
            bid = lines[word["line_id"]]["block_id"]
            hyphen_owners[word["hyphenation"]["group_id"]].append(owners[bid])
    for gid, memberships in hyphen_owners.items():
        if any(owner != memberships[0] for owner in memberships[1:]):
            errors.append(f"{gid}: hyphenation crosses source span/template ownership")
    return errors


def _tokens_by_block(page: dict) -> dict[str, list[str]]:
    """Reconstruct validated blocks once, preserving their internal reading order."""
    blocks = {block["id"]: block for block in page["blocks"]}
    lines = {line["id"]: line for line in page["lines"]}
    words = {word["id"]: word for word in page["words"]}
    result = {}
    for bid, block in blocks.items():
        tokens = []
        for lid in block["line_ids"]:
            for wid in lines[lid]["word_ids"]:
                word = words[wid]
                hyphen = word["hyphenation"]
                if hyphen is None:
                    tokens.append(word["text"])
                elif hyphen["part"] == "start":
                    tokens.append(hyphen["reconstructed_text"])
        result[bid] = tokens
    return result


def validate_text_provenance(page: dict, text_assets: dict[str, str]) -> list[str]:
    """Check declared source segments against the text of a structurally valid page.

    Call after validate_page has accepted ownership, order and hyphenation.
    Version 0.3 requires exact equality with the blocks bound to each span.
    Version 0.2 retains its occurrence check inside any single article (or
    unassigned block), without unique attribution, multiplicity or coverage.
    Both normalize only NFC/whitespace and explicitly annotated hyphenation.
    """
    blocks = {block["id"]: block for block in page["blocks"]}
    groups = [article["block_ids"] for article in page["articles"]]
    groups.extend([block["id"]] for block in blocks.values() if block["article_id"] is None)
    exact = page.get("schema_version") == "0.3.0"
    block_tokens = _tokens_by_block(page)
    sequences = [] if exact else [
        [token for bid in bids for token in block_tokens[bid]] for bids in groups
    ]
    errors = []
    for index, span in enumerate(page["provenance"]["text_spans"]):
        label = f"text span {index} ({span['asset_id']}:{span['start']}:{span['end']})"
        source = text_assets.get(span["asset_id"])
        if source is None:
            errors.append(f"{label}: source text unavailable")
            continue
        if not 0 <= span["start"] < span["end"] <= len(source):
            errors.append(f"{label}: invalid Unicode source bounds")
            continue
        expected = unicodedata.normalize("NFC", source[span["start"]:span["end"]]).split()
        if exact:
            actual = [token for bid in span["block_ids"] for token in block_tokens[bid]]
            if not expected or expected != actual:
                errors.append(f"{label}: source segment differs from exact bound block text")
        elif not expected or not any(
            sequence[start:start + len(expected)] == expected
            for sequence in sequences
            for start in range(len(sequence) - len(expected) + 1)
            if sequence[start] == expected[0]
        ):
            errors.append(f"{label}: source segment not found in composed article text")
    return errors


def _validate_template_text(page: dict, template: dict) -> list[str]:
    article_ids = page["provenance"].get("extensions", {}).get("mf:template_article_ids", [])
    if not article_ids:
        return []
    literal = template["metadata"].get("literal_text")
    if (
        not isinstance(literal, list)
        or not literal
        or any(not isinstance(text, str) or not text.strip() for text in literal)
    ):
        return ["template metadata.literal_text must be a nonempty list of literal strings"]
    articles = {a["id"]: a for a in page["articles"]}
    block_ids = [bid for aid in article_ids for bid in articles[aid]["block_ids"]]
    expected = unicodedata.normalize("NFC", " ".join(literal)).split()
    block_tokens = _tokens_by_block(page)
    actual = [token for bid in block_ids for token in block_tokens[bid]]
    if actual != expected:
        return ["template articles differ from exact template metadata.literal_text"]
    return []


def _partition_structure(value: dict, *, receipt: bool = False) -> list[str]:
    """Validate the versioned metadata format without reading corpus text."""
    name = {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,31}(?![\\s\\S])"}
    digest = {"type": "string", "pattern": "^[a-f0-9]{64}(?![\\s\\S])"}
    string = {"type": "string", "minLength": 1}
    strings = {"type": "array", "items": string, "uniqueItems": True}
    mapping = {"type": "object", "minProperties": 1, "propertyNames": name}
    if receipt:
        properties = {
            "version": {"const": "1"}, "name": name,
            "path": {"const": "provenance/partition.json"}, "sha256": digest,
            "source_catalog_path": {"const": "provenance/source-catalog.json"},
            "source_catalog_sha256": digest,
        }
    else:
        component = {
            "type": "object", "additionalProperties": False,
            "properties": {
                "key": digest, "partition": name,
                "groups": {**strings, "minItems": 1},
                "chars": {"type": "integer", "minimum": 1},
            },
            "required": ["key", "partition", "groups", "chars"],
        }
        properties = {
            "format": {"const": "mille-feuilles-partition"}, "version": {"const": "1"},
            "method": {"const": "components-sha256-greedy-v1"},
            "seed": {"type": "integer", "minimum": 0, "maximum": 2**53 - 1},
            "ratios": {**mapping, "additionalProperties": {"type": "number", "minimum": 0}},
            "catalog_sha256": digest,
            "partitions": {**mapping, "additionalProperties": strings},
            "components": {"type": "array", "minItems": 1, "items": component},
            "characters": {**mapping, "additionalProperties": {"type": "integer", "minimum": 0}},
        }
    schema = {"type": "object", "additionalProperties": False,
              "properties": properties, "required": list(properties)}
    return list(_finite_errors(value)) + [
        f"partition {'receipt' if receipt else 'plan'}.{'.'.join(map(str, error.path))}: {error.message}"
        for error in Draft202012Validator(schema).iter_errors(value)
    ]


def validate_partition_receipt(root: Path, manifest: dict, registry: dict) -> list[str]:
    """Check a filtered lot's receipt from metadata only, never excluded text.

    This proves consistency with the embedded source catalog and component plan.
    Recomputing the shared-unit graph requires the original complete bundle;
    metadata alone cannot prove that two excluded texts share no normalized unit.
    Page partition labels are checked separately when validate_dataset reads pages.
    """
    errors = _structural_errors(manifest, "manifest") + _structural_errors(registry, "assets")
    if errors:
        return errors
    artifacts = {item["path"]: item["sha256"] for item in manifest["artifacts"]}

    def read_hashed(relative, expected=None):
        if relative not in artifacts:
            errors.append(f"partition metadata missing artifact: {relative}")
        try:
            path = safe_path(root, relative)
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected is not None and actual != expected:
                errors.append(f"partition SHA-256 mismatch: {relative}")
            if relative in artifacts and artifacts[relative] != actual:
                errors.append(f"partition artifact SHA-256 mismatch: {relative}")
            return load_json(path)
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"cannot read partition metadata {relative!r}: {exc}")
            return None

    config = read_hashed(manifest["config"]["path"], manifest["config"]["sha256"])
    if not isinstance(config, dict):
        return errors + ["partition config must be an object"]
    render = config.get("render", {})
    if not isinstance(render, dict):
        return errors + ["partition config.render must be an object"]
    extensions = manifest.get("extensions", {})
    receipt = extensions.get("mf:partition")
    if "mf:partition" not in extensions:
        if render.get("partition") is not None or config.get("partition") is not None:
            errors.append("partition config requires a manifest mf:partition receipt")
        return errors
    issues = _partition_structure(receipt, receipt=True)
    if issues:
        return errors + issues
    name = receipt["name"]
    if manifest["schema_version"] != "0.3.0":
        errors.append("partition receipt requires dataset schema_version 0.3.0")
    if config.get("partition") != receipt or render.get("partition") != name:
        errors.append("partition config and manifest receipt/name differ")
    plan = read_hashed(receipt["path"], receipt["sha256"])
    source = read_hashed(receipt["source_catalog_path"], receipt["source_catalog_sha256"])
    selected = read_hashed("assets/catalog.json")
    stored_registry = read_hashed(manifest["assets"]["path"], manifest["assets"]["sha256"])
    if stored_registry != registry:
        errors.append("partition registry differs from the manifest registry file")
    issues = _partition_structure(plan)
    for catalog in (source, selected):
        issues += _structural_errors(catalog, "assets")
    if issues:
        return errors + issues
    if plan["catalog_sha256"] != receipt["source_catalog_sha256"]:
        errors.append("partition catalog_sha256 differs from source catalog receipt")
    ratios, partitions = plan["ratios"], plan["partitions"]
    try:
        total = math.fsum(ratios.values())
    except OverflowError:
        total = math.inf
    if not math.isfinite(total) or total <= 0:
        return errors + ["partition ratios must have a finite positive sum"]
    if set(ratios) != set(partitions) or set(plan["characters"]) != set(partitions):
        return errors + ["partition names differ between ratios, partitions and characters"]
    if name not in partitions or ratios[name] <= 0:
        return errors + ["receipt names an unknown or zero-weight partition"]

    def texts(catalog, label):
        identities = [asset["id"] for asset in catalog["assets"]]
        if len(identities) != len(set(identities)):
            errors.append(f"partition {label} has duplicate asset ids")
        return {asset["id"]: asset for asset in catalog["assets"] if asset["kind"] == "text"}

    original = texts(source, "source catalog")
    selected_texts = texts(selected, "selected catalog")
    registered = texts(registry, "registry")
    group_by_id, document_by_id = {}, {}
    for identity, asset in original.items():
        metadata = asset["metadata"]
        document = metadata.get("source_document_id")
        group = metadata.get("source_group_id", document)
        if not isinstance(document, str) or not document.strip():
            errors.append(f"partition source document id missing: {identity}")
        if not isinstance(group, str) or not group.strip():
            errors.append(f"partition source group id missing: {identity}")
        if source["schema_version"] == "0.3.0" and "source_group_id" not in metadata:
            errors.append(f"partition 0.3 source group id missing: {identity}")
        if metadata.get("role") not in ("body", "title", "advertisement"):
            errors.append(f"partition source role missing/unknown: {identity}")
        group_by_id[identity], document_by_id[identity] = group, document
    if errors:
        return errors
    membership = {}
    for partition, ids in partitions.items():
        if ids != sorted(ids):
            errors.append(f"partition asset ids must be sorted: {partition}")
        for identity in ids:
            if identity in membership:
                errors.append(f"partition asset appears in multiple partitions: {identity}")
            membership[identity] = partition
        roles = {original[identity]["metadata"]["role"] for identity in ids if identity in original}
        if ratios[partition] == 0:
            if ids:
                errors.append(f"zero-weight partition is not empty: {partition}")
        elif roles != {"body", "title", "advertisement"}:
            errors.append(f"positive partition lacks required text roles: {partition}")
    if set(membership) != set(original):
        return errors + ["partition asset ids do not cover source text assets exactly"]
    wanted = set(partitions[name])
    excluded_paths = {asset["path"] for identity, asset in original.items() if identity not in wanted}
    for relative in sorted(excluded_paths & set(artifacts)):
        errors.append(f"partition artifact contains excluded text: {relative}")
    for catalog, label in ((selected_texts, "selected catalog"), (registered, "registry")):
        if set(catalog) != wanted:
            errors.append(f"partition {label} text ids differ from selected partition")
        for identity, asset in catalog.items():
            if identity not in original:
                continue
            expected = original[identity]
            actual_metadata, expected_metadata = asset["metadata"], expected["metadata"]
            catalog_version = selected["schema_version"] if label == "selected catalog" else registry["schema_version"]
            if catalog_version == "0.3.0" and "source_group_id" not in actual_metadata:
                errors.append(f"partition {label} 0.3 source group id missing: {identity}")
            if any(asset[key] != expected[key] for key in ("id", "path", "sha256")) or any(
                actual_metadata.get(key) != expected_metadata.get(key)
                for key in ("source_document_id", "role")
            ) or actual_metadata.get("source_group_id", actual_metadata.get("source_document_id")) != group_by_id[identity]:
                errors.append(f"partition {label} selected asset differs from source catalog: {identity}")
    for label, values in (("group", group_by_id), ("document", document_by_id),
                          ("sha256", {key: asset["sha256"] for key, asset in original.items()})):
        owners = defaultdict(set)
        for identity, value in values.items():
            owners[value].add(membership[identity])
        if any(len(names) != 1 for names in owners.values()):
            errors.append(f"partition source {label} crosses partitions")
    group_partitions = {group: membership[identity] for identity, group in group_by_id.items()}
    component_groups, keys = Counter(), Counter()
    characters = Counter()
    for component in plan["components"]:
        groups = component["groups"]
        keys[component["key"]] += 1
        component_groups.update(groups)
        expected_key = hashlib.sha256("\x1f".join(sorted(groups)).encode()).hexdigest()
        if groups != sorted(groups) or component["key"] != expected_key:
            errors.append("partition component key/groups are not canonical")
        if component["partition"] not in partitions:
            errors.append("partition component names an unknown partition")
        if any(group_partitions.get(group) != component["partition"] for group in groups):
            errors.append("partition component groups disagree with asset assignments")
        characters[component["partition"]] += component["chars"]
    if set(component_groups) != set(group_partitions) or any(n != 1 for n in component_groups.values()):
        errors.append("partition components must cover source groups exactly once")
    if any(n != 1 for n in keys.values()):
        errors.append("partition component keys must be unique")
    if any(plan["characters"][key] != characters[key] for key in partitions):
        errors.append("partition characters differ from component totals")
    return errors


def validate_import_receipt(root: Path, manifest: dict) -> list[str]:
    """Bind an optional import report to its catalog using metadata only.

    Exclusion claims are retained, not re-evaluated: the protected inputs and
    excluded source texts are deliberately not read by this check.
    """
    errors = _structural_errors(manifest, "manifest")
    if errors or "mf:import_report" not in manifest.get("extensions", {}):
        return errors
    digest = {"type": "string", "pattern": "^[a-f0-9]{64}(?![\\s\\S])"}
    reference = manifest["extensions"]["mf:import_report"]
    reference_schema = {
        "type": "object", "additionalProperties": False,
        "properties": {"path": {"const": "provenance/import-report.json"}, "sha256": digest},
        "required": ["path", "sha256"],
    }
    errors += [f"import receipt: {issue.message}"
               for issue in Draft202012Validator(reference_schema).iter_errors(reference)]
    if errors:
        return errors

    def read_hashed(relative, expected=None):
        records = [item for item in manifest["artifacts"] if item["path"] == relative]
        if len(records) != 1:
            errors.append(f"import metadata requires exactly one artifact: {relative}")
        try:
            path = safe_path(root, relative)
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected is not None and actual != expected:
                errors.append(f"import receipt SHA-256 mismatch: {relative}")
            if len(records) == 1 and records[0]["sha256"] != actual:
                errors.append(f"import artifact SHA-256 mismatch: {relative}")
            return load_json(path)
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"cannot read import metadata {relative!r}: {exc}")
            return None

    report = read_hashed(reference["path"], reference["sha256"])
    item_properties = {
        "asset_id": {"type": "string", "minLength": 1},
        "source_document_id": {"type": "string", "minLength": 1},
        "source_group_id": {"type": "string", "minLength": 1},
        "role": {"enum": ["body", "title", "advertisement"]},
        "sha256": digest,
    }
    report_schema = {
        "type": "object",
        "properties": {
            "format": {"const": "mille-feuilles-import-report"},
            "version": {"const": "1"}, "status": {"const": "pass"},
            "accepted": {"type": "array", "minItems": 1, "items": {
                "type": "object", "properties": item_properties,
                "required": list(item_properties), "additionalProperties": False,
            }},
        },
        "required": ["format", "version", "status", "accepted"],
    }
    issues = [f"import report.{'.'.join(map(str, issue.path))}: {issue.message}"
              for issue in Draft202012Validator(report_schema).iter_errors(report)]
    if issues:
        return errors + issues
    partition = manifest.get("extensions", {}).get("mf:partition")
    if "mf:partition" in manifest.get("extensions", {}):
        issues = _partition_structure(partition, receipt=True)
        if issues:
            return errors + issues
        catalog = read_hashed(partition["source_catalog_path"], partition["source_catalog_sha256"])
    else:
        catalog = read_hashed("assets/catalog.json")
    issues = _structural_errors(catalog, "assets")
    if issues:
        return errors + issues
    if catalog["schema_version"] != "0.3.0":
        return errors + ["import receipt requires source catalog schema_version 0.3.0"]
    expected = [
        {"asset_id": asset["id"], "sha256": asset["sha256"],
         **{key: asset["metadata"][key] for key in ("source_document_id", "source_group_id", "role")}}
        for asset in catalog["assets"] if asset["kind"] == "text"
    ]
    for label, records in (("accepted", report["accepted"]), ("source catalog", expected)):
        for key in ("asset_id", "source_document_id", "sha256"):
            if len({item[key] for item in records}) != len(records):
                errors.append(f"import {label} has duplicate {key}")
    if sorted(report["accepted"], key=lambda item: item["asset_id"]) != sorted(
        expected, key=lambda item: item["asset_id"]
    ):
        errors.append("import accepted entries differ from source catalog text identities")
    return errors


def _partition_character_errors(root: Path, manifest: dict, registry: dict, texts: dict) -> list[str]:
    """Verify selected character totals after the metadata receipt has passed."""
    receipt = manifest.get("extensions", {}).get("mf:partition")
    if receipt is None:
        return []
    try:
        plan = load_json(safe_path(root, receipt["path"]))
    except (OSError, ValueError) as exc:
        return [f"cannot read partition character totals: {exc}"]
    errors = []
    by_group = Counter()
    for asset in registry["assets"]:
        if asset["kind"] != "text":
            continue
        if asset["id"] not in texts:
            errors.append(f"partition characters unavailable for text: {asset['id']}")
            continue
        metadata = asset["metadata"]
        group = metadata.get("source_group_id", metadata.get("source_document_id"))
        by_group[group] += len(texts[asset["id"]])
    for component in plan["components"]:
        if component["partition"] == receipt["name"]:
            actual = sum(by_group[group] for group in component["groups"])
            if actual != component["chars"]:
                errors.append(
                    "partition component characters differ from selected Unicode text: "
                    + component["key"]
                )
    if sum(by_group.values()) != plan["characters"][receipt["name"]]:
        errors.append(
            "partition characters differ from selected Unicode text total: " + receipt["name"]
        )
    return errors


def _load_degradation_profile(root: Path, manifest: dict, artifacts: set[str]):
    """Load the embedded, bounded profile without resolving a name outside the lot."""
    errors = []
    measured = manifest["profile"] in MEASURED_PROFILES
    try:
        config = load_json(safe_path(root, manifest["config"]["path"]))
        render = config.get("render", {}) if isinstance(config, dict) else None
        if not isinstance(render, dict):
            return None, ["degradation profile config.render must be an object"]
        declared = render.get("degradation_profile")
        expected_layout = LAYOUT_PROFILE if manifest["profile"] == LAYOUT_PROFILE else None
        if render.get("layout_profile") != expected_layout:
            errors.append("config.render.layout_profile differs from dataset profile")
        if not measured:
            if declared is not None:
                errors.append("degradation profile requires the measured dataset profile")
            return None, errors
        from .degrade import load_profile
        from .diagnostics import compare

        reference = manifest["extensions"]["mf:degradation_profile"]
        if reference["path"] not in artifacts:
            errors.append("degradation profile missing from artifact inventory")
        path = safe_path(root, reference["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]:
            errors.append("degradation profile file SHA-256 mismatch")
        profile = load_profile(path)
        if profile.get("calibrated") is not False:
            errors.append("invalid degradation profile: measured profile requires calibrated:false")
        if compare(declared, profile):
            errors.append("embedded degradation profile differs from config.render.degradation_profile")
        if type(render.get("seed")) is not int or render["seed"] != manifest["rng"]["seed"]:
            errors.append("degradation profile config seed differs from manifest RNG seed")
        return profile, errors
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return None, [f"invalid degradation profile: {exc}"]


def _measured_page_errors(root: Path, page: dict, profile: dict, seed: int,
                          index: int, artifacts: set[str]) -> list[str]:
    """Recompute diagnostics against the declared ideal mask, not ideal glyphs.

    Glyph-to-mask fidelity belongs to renderer tests and reproduction; a mask
    and diagnostics that were jointly replaced cannot establish that fidelity.
    """
    from .degrade import FAMILIES, degradation_seed, reference_levels, sample_parameters
    from .diagnostics import LEGIBILITY_METHOD, compare, diagnostics_path, document, load_mask, mask_path
    import numpy as np

    errors = []
    parameters = page["provenance"]["parameters"]
    resolved = parameters["degradation_profile"]
    expected = sample_parameters(profile, degradation_seed(seed, index))
    parameter_errors = compare(resolved, expected)
    if parameter_errors:
        return [f"degradation resolved parameters differ from seeded profile: {error}"
                for error in parameter_errors]
    factor = profile["oversampling"]
    width, height = page["image"]["width"], page["image"]["height"]
    for key, wanted in (("oversampling", factor), ("raster_width", width * factor),
                        ("raster_height", height * factor), ("legibility_method", LEGIBILITY_METHOD)):
        if compare(parameters.get(key), wanted):
            errors.append(f"measured parameter {key} differs from profile/final image")
    paper, ink = reference_levels(expected)
    for key, wanted in (("paper_level", paper), ("ink_level", ink),
                        ("blur_radius", expected.get("blur", {}).get("sigma_px", 0.0))):
        if compare(parameters.get(key), wanted):
            errors.append(f"measured parameter {key} differs from resolved degradation profile")
    angle = parameters.get("angle_degrees")
    if type(angle) not in (int, float) or not math.isfinite(angle) or not -0.35 <= angle <= 0.35:
        return errors + ["measured angle_degrees must be finite and within [-0.35, 0.35]"]
    theta = math.radians(angle)
    cosine, sine = math.cos(theta), math.sin(theta)
    cx, cy = width / 2, height / 2
    rotation = {
        "kind": "rotation",
        "geometry": {"matrix": [
            [cosine, sine, (cx - cosine * cx - sine * cy) * factor],
            [-sine, cosine, (cy + sine * cx - cosine * cy) * factor],
            [0, 0, 1],
        ]},
        "parameters": {"degrees": angle, "resampling": "bicubic",
                       "center": [cx * factor, cy * factor], "fill": 0},
    }
    scales = [transform for transform in page["transforms"]
              if transform["kind"] in ("mf:oversampling", "mf:downsample")]
    expected_scales = []
    if factor == 2:
        for kind, scale, source_size, target_size, extra in (
            ("mf:oversampling", 2, [width, height], [2 * width, 2 * height], {}),
            ("mf:downsample", 0.5, [2 * width, 2 * height], [width, height],
             {"resampling": "box-mean"}),
        ):
            expected_scales.append({
                "kind": kind, "geometry": {"matrix": [[scale, 0, 0], [0, scale, 0], [0, 0, 1]]},
                "parameters": {"factor": 2, "source_size": source_size, "target_size": target_size, **extra},
            })
    if compare(scales, expected_scales):
        errors.append("measured oversampling/downsample transforms disagree with profile")
    geometries = [transform for transform in page["transforms"]
                  if transform["geometry"] != "identity"]
    expected_geometry = [rotation] if factor == 1 else [expected_scales[0], rotation, expected_scales[1]]
    if compare(geometries, expected_geometry):
        errors.append("measured geometry sequence/matrix differs from declared rotation and raster")
    reference = page["extensions"]["mf:diagnostics"]
    if reference["path"] != diagnostics_path(page["page_id"]):
        errors.append("diagnostics path does not match page identity")
    if reference["mask_path"] != mask_path(page["page_id"]):
        errors.append("diagnostics mask path does not match page identity")
    if errors:
        return errors
    for relative, expected_sha in ((reference["path"], reference["sha256"]),
                                   (reference["mask_path"], reference["mask_sha256"])):
        if relative not in artifacts:
            errors.append(f"measured artifact missing from inventory: {relative}")
        try:
            path = safe_path(root, relative)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
                errors.append(f"measured artifact SHA-256 mismatch: {relative}")
        except (OSError, ValueError) as exc:
            errors.append(f"invalid measured artifact {relative}: {exc}")
    expected_families = [family for family in FAMILIES if family in expected]
    photometric = [transform for transform in page["transforms"]
                   if transform["kind"].startswith("mf:degrade:")]
    if [transform["kind"] for transform in photometric] != [
        f"mf:degrade:{family}" for family in expected_families
    ]:
        errors.append("degradation transforms do not match profile family order")
    else:
        max_pixels = width * height
        for family, transform in zip(expected_families, photometric):
            recorded = transform["parameters"]
            wanted = {**expected[family], "seed": expected["seed"],
                      "rng": "numpy.PCG64[seed, family]"}
            if family == "ink_loss":
                broken = recorded.get("broken_pixels")
                if type(broken) is not int or not 0 <= broken <= max_pixels or (
                    expected[family].get("break_density", 0) == 0 and broken != 0
                ):
                    errors.append("degradation ink_loss broken_pixels is invalid")
                wanted["broken_pixels"] = broken
            elif family == "blur":
                wanted["implementation"] = "Pillow GaussianBlur on 8-bit image"
            if transform["geometry"] != "identity" or compare(recorded, wanted):
                errors.append(f"degradation transform parameters disagree with resolved {family}")
    seen_photometry = False
    for transform in page["transforms"]:
        if transform["kind"].startswith("mf:degrade:"):
            seen_photometry = True
        elif transform["geometry"] == "identity":
            errors.append("undeclared photometric transform in measured profile")
        elif seen_photometry:
            errors.append("geometric transform follows measured photometric transforms")
    if errors:
        return errors
    try:
        image_ref = page["image"]
        image_path = safe_path(root, image_ref["path"])
        actual_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
        if actual_sha != image_ref["sha256"]:
            return ["diagnostics input image SHA-256 mismatch"]
        with Image.open(image_path) as image:
            if image.format != "PNG" or image.mode != "L" or image.size != (
                image_ref["width"], image_ref["height"]
            ):
                return ["measured diagnostics require an L PNG at final page dimensions"]
            pixels = np.asarray(image, dtype=np.uint8).copy()
        mask = load_mask(safe_path(root, reference["mask_path"]), pixels.shape)
        support = Image.new("L", (image_ref["width"], image_ref["height"]), 0)
        drawing = ImageDraw.Draw(support)
        for block in page["blocks"]:
            drawing.polygon([tuple(point) for point in block["polygon"]], fill=255)
        allowed = np.asarray(support.filter(ImageFilter.MaxFilter(7)), dtype=bool)
        if np.any(mask & ~allowed):
            return ["ideal mask has ink outside all block polygons (3 px tolerance)"]
        stored = load_json(safe_path(root, reference["path"]))
        recomputed = document(pixels, mask, page, image_sha256=actual_sha,
                              mask_sha256=reference["mask_sha256"])
        errors.extend(f"recomputed diagnostics: {error}" for error in compare(stored, recomputed))
        if set(recomputed["words"]) != {word["id"] for word in page["words"]}:
            errors.append("recomputed diagnostics word ids differ from canonical words")
        for word in page["words"]:
            if word["legibility"] != recomputed["words"][word["id"]]["legibility"]:
                errors.append(f"{word['id']}: legibility differs from recomputed diagnostics")
    except (OSError, ValueError, TypeError, KeyError, SyntaxError, Image.DecompressionBombError) as exc:
        errors.append(f"invalid measured diagnostics: {exc}")
    return errors


def validate_dataset(root: Path, verify_exports: bool = True) -> dict:
    """Audit hashes, assets, canonical annotations, images and optional exports."""
    try:
        root = Path(root).resolve()
    except (OSError, RuntimeError) as exc:
        detail = f"cannot resolve dataset root: {exc}"
        return {
            "status": "fail",
            "errors": [detail],
            "checks": [{"name": "root", "status": "fail", "detail": detail}],
        }
    errors, checks = [], []

    def check(name, issues, detail=""):
        issues = list(issues)
        errors.extend(f"{name}: {item}" for item in issues)
        checks.append(
            {
                "name": name,
                "status": "fail" if issues else "pass",
                "detail": "; ".join(issues) if issues else detail or "verified",
            }
        )

    def read(relative):
        return load_json(safe_path(root, relative))

    def hashed(relative, expected):
        try:
            path = safe_path(root, relative)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return [] if digest == expected else [f"SHA-256 mismatch: {relative}"]
        except (OSError, ValueError) as exc:
            return [f"cannot verify {relative!r}: {exc}"]

    def result():
        return {"status": "fail" if errors else "pass", "errors": errors, "checks": checks}

    try:
        manifest = read("manifest.json")
        issues = _structural_errors(manifest, "manifest")
        check("manifest", issues)
        if issues:
            return result()
    except (OSError, ValueError, TypeError) as exc:
        check("manifest", [str(exc)])
        return result()
    refs = [
        (manifest["config"]["path"], manifest["config"]["sha256"]),
        (manifest["assets"]["path"], manifest["assets"]["sha256"]),
        (manifest["generator"]["environment_path"], manifest["generator"]["environment_sha256"]),
        (manifest["calibration"]["protocol_path"], manifest["calibration"]["protocol_sha256"]),
        (
            manifest["calibration"]["files_read"]["path"],
            manifest["calibration"]["files_read"]["sha256"],
        ),
    ]
    refs += [(r["path"], r["sha256"]) for r in manifest["pages"] + manifest["artifacts"]]
    check("file_hashes", [e for path, sha in refs for e in hashed(path, sha)])
    json_issues = []
    for relative in sorted({p for p, _ in refs if p.endswith(".json")}):
        try:
            read(relative)
        except (OSError, ValueError, TypeError) as exc:
            json_issues.append(f"{relative}: {exc}")
    check("strict_json_files", json_issues)
    check(
        "unique_manifest_entries",
        [
            f"duplicate {field}: {value}"
            for rows, field in (
                (manifest["pages"], "id"),
                (manifest["pages"], "path"),
                (manifest["artifacts"], "path"),
            )
            for value, count in Counter(row[field] for row in rows).items()
            if count != 1
        ],
    )
    artifact_paths = {r["path"] for r in manifest["artifacts"]}
    check(
        "manifest_coverage",
        [f"missing artifact entry: {path}" for path, _ in refs[:5] if path not in artifact_paths]
        + [
            f"circular/report artifact forbidden: {p}"
            for p in artifact_paths
            if p in ("manifest.json", "qa/report.json")
        ],
    )
    if "mf:import_report" in manifest.get("extensions", {}):
        check("import_receipt", validate_import_receipt(root, manifest),
              "import/catalog metadata consistency verified; exclusions not re-evaluated")
    try:
        registry = read(manifest["assets"]["path"])
        issues = _structural_errors(registry, "assets")
        check("asset_registry", issues)
        if issues:
            return result()
    except (OSError, ValueError, TypeError) as exc:
        check("asset_registry", [str(exc)])
        return result()
    assets = {a["id"]: a for a in registry["assets"]}
    partition_issues = validate_partition_receipt(root, manifest, registry)
    check(
        "partition_receipt", partition_issues,
        "metadata consistency verified; full graph replay requires the complete source bundle"
        if "mf:partition" in manifest.get("extensions", {})
        else "unpartitioned dataset; no partition isolation claim",
    )
    asset_issues = [
        f"duplicate asset id: {identity}"
        for identity, count in Counter(a["id"] for a in registry["assets"]).items()
        if count > 1
    ]
    text_assets = {}
    for asset in registry["assets"]:
        asset_issues += hashed(asset["path"], asset["sha256"])
        if asset["path"] not in artifact_paths:
            asset_issues.append(f"missing asset artifact: {asset['path']}")
        rights = asset["rights"]
        if rights["status"] != "verified" or not rights["redistribution_allowed"]:
            asset_issues.append(f"unverified/nonredistributable asset: {asset['id']}")
        evidence_files = asset["metadata"].get("evidence_files", [])
        if not isinstance(evidence_files, list):
            asset_issues.append(f"{asset['id']}: evidence_files must be a list")
            evidence_files = []
        for evidence in evidence_files:
            if (
                not isinstance(evidence, dict)
                or not isinstance(evidence.get("path"), str)
                or not isinstance(evidence.get("sha256"), str)
                or len(evidence["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in evidence["sha256"])
            ):
                asset_issues.append(
                    f"{asset['id']}: evidence_files entries require path and SHA-256"
                )
                continue
            asset_issues += hashed(evidence["path"], evidence["sha256"])
            if evidence["path"] not in artifact_paths:
                asset_issues.append(f"missing evidence artifact: {evidence['path']}")
        evidence_uri = rights["evidence_uri"]
        try:
            scheme = urlsplit(evidence_uri).scheme
            if scheme == "file" or len(scheme) == 1:
                asset_issues.append(
                    f"{asset['id']}: local evidence_uri must be a relative dataset path"
                )
            elif not scheme:
                # A local notice is required even when it is declared only in
                # rights.evidence_uri rather than repeated in evidence_files.
                local_evidence = safe_path(root, evidence_uri)
                if not local_evidence.is_file():
                    asset_issues.append(f"missing local rights evidence: {evidence_uri}")
                if evidence_uri not in artifact_paths:
                    asset_issues.append(f"missing evidence artifact: {evidence_uri}")
        except (OSError, ValueError) as exc:
            asset_issues.append(f"invalid rights evidence: {exc}")
        if asset["kind"] == "text":
            if not asset["metadata"].get("source_document_id"):
                asset_issues.append(f"text asset missing source_document_id: {asset['id']}")
            try:
                text_assets[asset["id"]] = safe_path(root, asset["path"]).read_text(
                    encoding="utf-8"
                )
            except (OSError, ValueError) as exc:
                asset_issues.append(str(exc))
    check("assets", asset_issues)
    if not partition_issues and "mf:partition" in manifest.get("extensions", {}):
        check("partition_characters", _partition_character_errors(root, manifest, registry, text_assets))
    degradation_profile, degradation_issues = _load_degradation_profile(root, manifest, artifact_paths)
    if degradation_issues or manifest["profile"] in MEASURED_PROFILES:
        check("degradation_profile", degradation_issues)
    layout_context, layout_issues = _load_layout_context(root, manifest, assets)
    if layout_issues or manifest["profile"] == LAYOUT_PROFILE:
        check("layout_profile", layout_issues)
    pages = []
    for index, record in enumerate(manifest["pages"]):
        try:
            page = read(record["path"])
            issues = validate_page(page)
            check(f"page:{record['id']}", issues)
            if issues:
                continue
            page_issues = []
            if page["profile"] not in MEASURED_PROFILES and any(
                word["legibility"] != "readable" for word in page["words"]
            ):
                page_issues.append("pilot profile excludes uncertain/illegible word supervision")
            if page["page_id"] != record["id"] or page["profile"] != manifest["profile"]:
                page_issues.append("page identity/profile differs from manifest")
            if page["schema_version"] != manifest["schema_version"]:
                page_issues.append("page schema_version differs from manifest")
            provenance = page["provenance"]
            if page["profile"] in MEASURED_PROFILES:
                if degradation_profile is None or degradation_issues:
                    page_issues.append("measured page requires a valid embedded degradation profile")
                else:
                    page_issues += _measured_page_errors(
                        root, page, degradation_profile, manifest["rng"]["seed"], index, artifact_paths
                    )
            elif provenance["parameters"].get("degradation_profile") is not None:
                page_issues.append("degradation parameters require the measured page profile")
            receipt = manifest.get("extensions", {}).get("mf:partition")
            expected_partition = receipt.get("name") if isinstance(receipt, dict) else None
            if provenance["parameters"].get("partition") != expected_partition:
                page_issues.append("page partition differs from manifest partition receipt")
            for asset_id in provenance["asset_ids"]:
                if asset_id not in assets:
                    page_issues.append(f"unknown provenance asset: {asset_id}")
            template = assets.get(provenance["template_id"])
            if (
                template is None
                or template["kind"] != "template"
                or template["id"] not in provenance["asset_ids"]
            ):
                page_issues.append("template_id must reference a declared template asset")
            elif page["schema_version"] == "0.3.0":
                page_issues += _validate_template_text(page, template)
                if page["profile"] == LAYOUT_PROFILE:
                    if layout_context is None or layout_issues:
                        page_issues.append("layout: page requires valid copied template/config")
                    else:
                        page_issues += _layout_template_errors(root, page, template, layout_context)
            source_documents = set()
            source_groups = set()
            for span in provenance["text_spans"]:
                asset = assets.get(span["asset_id"])
                if asset is None or asset["kind"] != "text":
                    page_issues.append(
                        f"text span references unknown/nontext asset: {span['asset_id']}"
                    )
                    continue
                source_documents.add(span["source_document_id"])
                if span["source_document_id"] != asset["metadata"].get("source_document_id"):
                    page_issues.append("text span source_document_id differs from asset")
                if page["schema_version"] == "0.3.0":
                    group = asset["metadata"].get("source_group_id")
                    if not isinstance(group, str) or not group.strip():
                        page_issues.append(f"used text asset missing source_group_id: {asset['id']}")
                    else:
                        source_groups.add(group)
                if span["end"] > len(text_assets.get(span["asset_id"], "")):
                    page_issues.append("text span exceeds Unicode source length")
            page_issues += validate_text_provenance(page, text_assets)
            if page["schema_version"] == "0.3.0":
                if source_groups != set(record["source_group_ids"]):
                    page_issues.append("source_group_ids differ from exact used source groups")
            elif not source_documents.issubset(set(record["source_group_ids"])):
                page_issues.append("source_group_ids omit source text documents")
            image = page["image"]
            page_issues += hashed(image["path"], image["sha256"])
            if image["path"] not in artifact_paths:
                page_issues.append("image missing from artifact inventory")
            try:
                with Image.open(safe_path(root, image["path"])) as actual:
                    if (
                        actual.format != "PNG"
                        or actual.size != (image["width"], image["height"])
                        or actual.mode != image["color_mode"]
                    ):
                        page_issues.append("actual PNG dimensions/mode disagree with annotation")
                    dpi = actual.info.get("dpi")
                    if dpi and any(abs(float(d) - image["dpi"]) > 0.1 for d in dpi):
                        page_issues.append("PNG resolution metadata disagrees with annotation")
                    actual.verify()
            except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
                page_issues.append(f"invalid image: {exc}")
            qa_relative = f"qa/{record['id']}.png"
            if qa_relative not in artifact_paths:
                page_issues.append(f"missing QA artifact: {qa_relative}")
            try:
                with Image.open(safe_path(root, qa_relative)) as qa_image:
                    qa_width, qa_height = qa_image.size
                    width, height = image["width"], image["height"]
                    if qa_image.format != "PNG":
                        page_issues.append(f"QA overlay is not a PNG: {qa_relative}")
                    if not (
                        min(400, width) <= qa_width <= width
                        and min(400, height) <= qa_height <= height
                        and abs(qa_width * height - qa_height * width) <= max(width, height)
                    ):
                        page_issues.append(
                            f"QA overlay dimensions/aspect do not preserve the page: {qa_relative}"
                        )
                    qa_image.verify()
                # PNG.verify checks chunk integrity; decode also checks that
                # the compressed raster can actually be displayed.
                with Image.open(safe_path(root, qa_relative)) as qa_image:
                    qa_image.load()
            except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
                page_issues.append(f"invalid QA overlay {qa_relative}: {exc}")
            check(f"page_files:{record['id']}", page_issues)
            pages.append(page)
        except (OSError, ValueError, TypeError) as exc:
            check(f"page:{record['id']}", [str(exc)])
    if verify_exports:
        export_paths = {"exports/coco/instances.json"}
        for record in manifest["pages"]:
            pid = record["id"]
            export_paths.update(
                {
                    f"exports/page/{pid}.xml",
                    f"exports/alto/{pid}.xml",
                    f"exports/reports/{pid}.json",
                }
            )
        export_issues = []
        for relative in sorted(export_paths):
            if relative not in artifact_paths:
                export_issues.append(f"missing export artifact: {relative}")
            try:
                safe_path(root, relative)
            except ValueError as exc:
                export_issues.append(str(exc))
        check("export_inventory", export_issues)
        if len(pages) != len(manifest["pages"]):
            check("exports", ["canonical pages invalid; export verification cannot proceed"])
        elif errors:
            # Export readers cannot safely follow untrusted image or mapping paths.
            check("exports", ["dataset prerequisites failed; export verification cannot proceed"])
        else:
            try:
                from .exports import validate_exports

                check("exports", validate_exports(root, pages))
            except (OSError, ValueError, TypeError, ImportError) as exc:
                check("exports", [str(exc)])
    else:
        checks.append(
            {
                "name": "exports",
                "status": "not_run",
                "detail": "explicitly disabled; not a complete release audit",
            }
        )
    return result()


_LAYOUT_EPSILON = 1e-5  # Six-decimal planner rounding, not the 0.5 px final polygon tolerance.
_LAYOUT_PLAN_KEYS = {
    "version", "width", "height", "margin", "gutter", "zones", "zone_rules",
    "rez_de_chaussee_share", "min_zone_height",
}
_LAYOUT_ZONE_KEYS = {"id", "bbox", "columns", "headline_span", "headline_reserved",
                     "headline_body_band"}


def _layout_finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _layout_numbers(value, length):
    return isinstance(value, list) and len(value) == length and all(_layout_finite(v) for v in value)


def _layout_close(first, second):
    return abs(first - second) <= _LAYOUT_EPSILON


def _check_layout_plan(plan, *, width, height):
    """Return errors, including malformed JSON-like values, without throwing.

    This intentionally checks the actual declared planner's output: full-width,
    evenly spaced columns; 2 px centered zone rule; share and placement agree.
    It does not prove RNG replay, fit of a source word, or historical realism.
    """
    errors = []
    if type(width) is not int or type(height) is not int or not _layout_finite(width) or not _layout_finite(height) \
            or width <= 0 or height <= 0:
        return ["layout: invalid page dimensions"]
    if not isinstance(plan, dict) or set(plan) != _LAYOUT_PLAN_KEYS:
        return ["layout: exact plan keys required"]
    if plan["version"] != "1":
        errors.append("layout: unsupported version")
    if type(plan["height"]) is not int or plan["height"] != height:
        errors.append("layout: height must equal image.height")
    margin, gutter, minimum = (plan[k] for k in ("margin", "gutter", "min_zone_height"))
    if type(plan["width"]) is not int or plan["width"] != width:
        errors.append("layout: width must equal image.width")
    if type(margin) is not int or not _layout_finite(margin) or not 0 <= margin < width / 2:
        return errors + ["layout: invalid margin"]
    if not _layout_finite(gutter) or gutter < 0:
        return errors + ["layout: invalid gutter"]
    if not _layout_finite(minimum) or minimum <= 0:
        return errors + ["layout: min_zone_height must be positive and finite"]
    zones, rules = plan["zones"], plan["zone_rules"]
    if not isinstance(zones, list) or len(zones) not in (1, 2):
        return errors + ["layout: one or two zones required"]
    if not isinstance(rules, list) or len(rules) != len(zones) - 1 \
            or not all(_layout_numbers(r, 4) for r in rules):
        return errors + ["layout: exact four-coordinate zone rule per boundary required"]
    for index, zone in enumerate(zones):
        if not isinstance(zone, dict) or set(zone) != _LAYOUT_ZONE_KEYS:
            return errors + ["layout: exact zone keys required"]
        label = ("main", "rez_de_chaussee")[index]
        if zone["id"] != label:
            errors.append("layout: zones must be main then rez_de_chaussee")
        bbox, columns, span = (zone[k] for k in ("bbox", "columns", "headline_span"))
        if not _layout_numbers(bbox, 4):
            return errors + [f"layout {label}: finite four-coordinate bbox required"]
        x0, y0, x1, y1 = bbox
        if not (_layout_close(x0, margin) and _layout_close(x1, width - margin) and margin <= y0 < y1 <= height - margin):
            errors.append(f"layout {label}: full-width bbox must be inside image")
        if y1 - y0 + _LAYOUT_EPSILON < minimum:
            errors.append(f"layout {label}: zone below declared minimum height")
        if not isinstance(columns, list) or not 2 <= len(columns) <= 6 \
                or not all(_layout_numbers(c, 2) for c in columns):
            return errors + [f"layout {label}: two to six finite column intervals required"]
        column_width = (width - 2 * margin - (len(columns) - 1) * gutter) / len(columns)
        if not _layout_finite(column_width) or column_width <= 0:
            return errors + [f"layout {label}: non-positive column width"]
        for ordinal, (left, right) in enumerate(columns):
            expected = margin + ordinal * (column_width + gutter)
            if not (left < right and _layout_close(left, expected) and _layout_close(right, expected + column_width)):
                errors.append(f"layout {label}: columns differ from uniform planned geometry")
        if span is not None and (label != "main" or type(span) is not int
                                 or not 2 <= span < len(columns)):
            errors.append(f"layout {label}: invalid headline span")
        reserved = zone["headline_reserved"]
        if reserved is not None:
            if not _layout_numbers(reserved, 4) or type(span) is not int or not 2 <= span < len(columns):
                errors.append(f"layout {label}: invalid headline reservation")
            elif not (_layout_close(reserved[0], columns[0][0]) and _layout_close(reserved[1], y0)
                      and _layout_close(reserved[2], columns[span - 1][1]) and y0 < reserved[3] < y1):
                errors.append(f"layout {label}: headline reservation outside planned columns")
        band = zone["headline_body_band"]
        if band is not None:
            if not _layout_numbers(band, 4) or not _layout_numbers(reserved, 4) or type(span) is not int \
                    or not 2 <= span < len(columns):
                errors.append(f"layout {label}: invalid headline body band")
            elif not (all(_layout_close(actual, wanted) for actual, wanted in
                          zip(band[:3], [reserved[0], reserved[3], reserved[2]]))
                      and band[1] < band[3] < y1):
                errors.append(f"layout {label}: body band outside headline columns/reservation/zone")
    share = plan["rez_de_chaussee_share"]
    if len(zones) == 1:
        if share is not None:
            errors.append("layout: share must be null without rez_de_chaussee")
        return errors
    if not _layout_finite(share) or not 0.05 <= share <= 0.6:
        return errors + ["layout: invalid rez_de_chaussee share"]
    if len(zones[0]["columns"]) == len(zones[1]["columns"]):
        errors.append("layout: lower zone must have a different column count")
    main, lower = [z["bbox"] for z in zones]
    gap = lower[1] - main[3]
    if not 4 <= gap <= 64 or not _layout_close(gap, round(gap)):
        errors.append("layout: zone gap must be an integer in 4..64")
    split = round(lower[3] - share * (lower[3] - main[1]), 6)
    if not (_layout_close(main[3], split - gap / 2) and _layout_close(lower[1], split + gap / 2)):
        errors.append("layout: declared share disagrees with zone placement")
    expected_rule = [margin, split - 1, width - margin, split + 1]
    if not all(_layout_close(actual, expected) for actual, expected in zip(rules[0], expected_rule)):
        errors.append("layout: zone rule must be full-width, centered and exactly 2 px")
    return errors


# Area is in square pixels, distinct from TOLERANCE (a linear buffer in pixels).
_LAYOUT_RULE_TEXT_AREA_TOLERANCE = 0.5


def _layout_page_errors(page: dict) -> list[str]:
    """Check v2 plan bindings in composition coordinates, before affine rotation.

    Called only after structural validation. These checks establish declared
    geometry and ownership, not glyph fidelity or replay of random choices.
    """
    import numpy as np

    parameters = page["provenance"]["parameters"]
    plan = parameters["layout"]
    errors = _check_layout_plan(plan, width=page["image"]["width"], height=page["image"]["height"])
    if errors:
        return errors
    zones = {zone["id"]: zone for zone in plan["zones"]}
    typography = parameters["layout_typography"]
    if parameters["layout_termination_rejections"] != {name: 32 for name in zones}:
        errors.append("layout: terminal rejection counts must be 32 for exactly the planned zones")
    if set(typography) != set(zones):
        return ["layout: typography zone ids differ from plan"]
    for key, wanted in (("columns", len(zones["main"]["columns"])), ("margin", plan["margin"]),
                        ("gutter", plan["gutter"]),
                        ("body_font_size", typography["main"]["normal_body_size"]),
                        ("line_spacing", typography["main"]["line_spacing_normal"])):
        if parameters.get(key) != wanted:
            errors.append(f"layout: {key} differs from plan/main typography")
    ratio = parameters["layout_body_ratio"]
    main_width = zones["main"]["columns"][0][1] - zones["main"]["columns"][0][0]
    expected_normal = max(10, round(main_width / ratio))
    for name, zone in zones.items():
        if typography[name]["normal_body_size"] != expected_normal:
            errors.append(f"layout {name}: normal body differs from main width/ratio")
        if typography[name]["small_body_size"] > expected_normal:
            errors.append(f"layout {name}: small body exceeds normal body")
        if typography[name] != typography["main"]:
            errors.append(f"layout {name}: all zones must share main typography")
        band = zone["headline_body_band"]
        if band is not None and zone["bbox"][3] - band[3] + _LAYOUT_EPSILON < typography[name]["line_spacing_normal"]:
            errors.append(f"layout {name}: headline band leaves less than one normal interline")
    minimum = 6 * max(item["line_spacing_normal"] for item in typography.values())
    if not _layout_close(plan["min_zone_height"], minimum):
        errors.append("layout: minimum zone height differs from six normal interlines")
    matrix = np.eye(3)
    try:
        for transform in page["transforms"]:
            if transform["geometry"] != "identity":
                matrix = np.asarray(transform["geometry"]["matrix"], dtype=float) @ matrix
        inverse = np.linalg.inv(matrix)
        if not np.isfinite(inverse).all() or not np.allclose(inverse[2], [0, 0, 1], rtol=0, atol=1e-10):
            return errors + ["layout: cannot invert declared affine geometry"]
    except (ValueError, OverflowError, np.linalg.LinAlgError):
        return errors + ["layout: cannot invert declared affine geometry"]
    coefficients = [inverse[0, 0], inverse[0, 1], inverse[1, 0], inverse[1, 1],
                    inverse[0, 2], inverse[1, 2]]
    blocks = {block["id"]: block for block in page["blocks"]}
    lines = {line["id"]: line for line in page["lines"]}
    polygons = {bid: affine_transform(Polygon(block["polygon"]), coefficients)
                for bid, block in blocks.items()}
    articles = {article["id"]: article for article in page["articles"]}
    template_ids = page["provenance"].get("extensions", {}).get("mf:template_article_ids", [])
    order = list(dict.fromkeys(blocks[bid]["article_id"] for bid in page["reading_order"]["block_ids"]
                               if bid in blocks))
    zone_articles = {name: [] for name in zones}
    ranks, saw_article, boxed_rules = [], False, set()
    for aid in order:
        article = articles.get(aid)
        if article is None:
            continue  # Generic ownership validation already reports this.
        if aid in template_ids:
            if saw_article:
                errors.append("layout: template articles must precede content zones")
            for bid in article["block_ids"]:
                if bid in polygons and polygons[bid].bounds[3] > zones["main"]["bbox"][1] + TOLERANCE:
                    errors.append(f"layout {bid}: template content overlaps planned content zone")
            continue
        saw_article = True
        meta = article.get("extensions", {}).get("mf:layout")
        if not isinstance(meta, dict) or meta.get("zone_id") not in zones:
            errors.append(f"layout {aid}: article requires a known zone binding")
            continue
        name = meta["zone_id"]
        zone_articles[name].append(aid)
        ranks.append(list(zones).index(name))
        zone = zones[name]
        normal, small = (typography[name][k] for k in ("normal_body_size", "small_body_size"))
        requested = meta["small_body_requested"]
        expected_size = small if requested else normal
        if meta["body_font_size"] != expected_size or meta["small_body"] != (requested and small < normal):
            errors.append(f"layout {aid}: requested/effective small body or body size inconsistent")
        owned = [bid for bid in article["block_ids"] if bid in blocks]
        headline = meta["headline"]
        hid = headline["block_id"] if headline else None
        if headline:
            if name != "main" or zone["headline_span"] is None or not owned or hid != owned[0] \
                    or hid not in blocks or blocks[hid]["category"] != "titre":
                errors.append(f"layout {aid}: wide headline must be first title block in main")
            elif (headline["reservation_bbox"] != zone["headline_reserved"]
                  or headline["body_column_indices"] != list(range(zone["headline_span"]))):
                errors.append(f"layout {aid}: headline reservation/columns differ from plan")
            else:
                reserve = box(*headline["reservation_bbox"])
                if not reserve.buffer(TOLERANCE).covers(polygons[hid]):
                    errors.append(f"layout {hid}: real title polygon outside reservation")
                title_width = polygons[hid].bounds[2] - polygons[hid].bounds[0]
                column_width = zone["columns"][0][1] - zone["columns"][0][0]
                if title_width <= column_width + plan["gutter"] - _LAYOUT_EPSILON:
                    errors.append(f"layout {hid}: wide title must exceed one column plus gutter")
                title_lines = [affine_transform(Polygon(lines[lid]["polygon"]), coefficients)
                               for lid in blocks[hid]["line_ids"] if lid in lines]
                if title_lines:
                    bounds = (min(p.bounds[0] for p in title_lines), min(p.bounds[1] for p in title_lines),
                              max(p.bounds[2] for p in title_lines), max(p.bounds[3] for p in title_lines))
                    if polygons[hid].hausdorff_distance(box(*bounds)) > TOLERANCE:
                        errors.append(f"layout {hid}: title polygon inflated beyond its line envelope")
        used_columns = []
        for bid in owned:
            polygon, block = polygons[bid], blocks[bid]
            if not box(*zone["bbox"]).buffer(TOLERANCE).covers(polygon):
                errors.append(f"layout {bid}: block outside its article zone")
            if bid != hid:
                candidates = []
                for column, (left, right) in enumerate(zone["columns"]):
                    top, bottom = zone["bbox"][1], zone["bbox"][3]
                    if zone["headline_span"] and column < zone["headline_span"]:
                        band = zone["headline_body_band"]
                        if zone["headline_reserved"] is None or band is None:
                            errors.append(f"layout {name}: final headline reservation/body band missing")
                            continue
                        if headline:
                            top = zone["headline_reserved"][3]
                            spacing = typography[name]["line_spacing_small" if requested else "line_spacing_normal"]
                            # Preparation envelopes are shared between raster factors;
                            # final ink may end earlier. Only containment is asserted.
                            bottom = band[3] - 0.6 * spacing
                        else:
                            top = band[3]
                    if box(left, top, right, bottom).buffer(TOLERANCE).covers(polygon):
                        candidates.append(column)
                if len(candidates) != 1:
                    errors.append(f"layout {bid}: block does not fit exactly one available column")
                else:
                    used_columns.append(candidates[0])
                    if headline and candidates[0] not in headline["body_column_indices"]:
                        errors.append(f"layout {bid}: body left the headline's reserved columns")
            if block["category"] in {"texte", "annonce"}:
                for lid in block["line_ids"]:
                    font = lines.get(lid, {}).get("extensions", {}).get("mf:font", {})
                    allowed_sizes = {expected_size}
                    if block["category"] == "annonce":
                        # Announcement headings retain category annonce. Dataset
                        # validation disambiguates title/body via source roles.
                        allowed_sizes.add(max(12, round(expected_size * 1.25)))
                    if font.get("size") not in allowed_sizes:
                        errors.append(f"layout {lid}: body line size differs from article")
        if used_columns != sorted(used_columns):
            errors.append(f"layout {aid}: article flows backwards through columns")
        if headline:
            body = [bid for bid in owned if bid != hid]
            counts = [len(blocks[bid]["line_ids"]) for bid in body]
            wanted_columns = list(range(zone["headline_span"] or 0))
            if (used_columns != wanted_columns or len(body) != len(wanted_columns)
                    or any(blocks[bid]["category"] != "texte" for bid in body)):
                errors.append(f"layout {aid}: headline body requires one block in every spanned column")
            if not counts or min(counts) < 2 or max(counts) - min(counts) > 1 or counts != sorted(counts, reverse=True):
                errors.append(f"layout {aid}: headline body needs balanced columns with at least two lines each")
        framing = meta["box"]
        if framing:
            if not owned or any(blocks[bid]["category"] != "annonce" for bid in owned):
                errors.append(f"layout {aid}: frame only permitted for advertisement article")
            if len(set(used_columns)) != 1:
                errors.append(f"layout {aid}: boxed advertisement must remain in one column")
            x0, y0, x1, y1 = framing["bbox"]
            if owned:
                bounds = [min(polygons[bid].bounds[0] for bid in owned),
                          min(polygons[bid].bounds[1] for bid in owned),
                          max(polygons[bid].bounds[2] for bid in owned),
                          max(polygons[bid].bounds[3] for bid in owned)]
                pad = framing["padding"] + 2
                expected = [bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad]
                if any(abs(actual - wanted) > TOLERANCE for actual, wanted in zip(framing["bbox"], expected)):
                    errors.append(f"layout {aid}: frame bbox differs from real text envelope plus padding")
            edges = [(x0, y0, x1, y0 + 2), (x1 - 2, y0, x1, y1),
                     (x0, y1 - 2, x1, y1), (x0, y0, x0 + 2, y1)]
            for rid, edge in zip(framing["rule_ids"], edges):
                if rid in boxed_rules:
                    errors.append(f"layout {rid}: frame rule reused by multiple advertisements")
                boxed_rules.add(rid)
                if rid not in blocks or blocks[rid]["category"] != "separateur" \
                        or blocks[rid]["article_id"] is not None or polygons[rid].hausdorff_distance(box(*edge)) > TOLERANCE:
                    errors.append(f"layout {rid}: frame rule missing, owned or geometrically incorrect")
            if used_columns:
                column = used_columns[0]
                left, right = zone["columns"][column]
                top = zone["bbox"][1]
                if zone["headline_body_band"] and column < zone["headline_span"]:
                    top = zone["headline_body_band"][3]
                if not box(left, top, right, zone["bbox"][3]).buffer(TOLERANCE).covers(box(*framing["bbox"])):
                    errors.append(f"layout {aid}: frame leaves its column")
    if ranks != sorted(ranks):
        errors.append("layout: reading order must finish main before rez_de_chaussee")
    for name, zone in zones.items():
        ids = zone_articles[name]
        if not ids:
            errors.append(f"layout {name}: zone contains no article")
        headlines = [aid for aid in ids if articles[aid]["extensions"]["mf:layout"]["headline"]]
        expected = ids[:1] if zone["headline_span"] is not None else []
        if headlines != expected or (zone["headline_span"] is not None and
                                     (zone["headline_reserved"] is None or zone["headline_body_band"] is None)):
            errors.append(f"layout {name}: wide headline must belong to first zone article")
    rules = {bid: poly for bid, poly in polygons.items() if blocks[bid]["category"] == "separateur"}
    text = {bid: poly for bid, poly in polygons.items() if blocks[bid]["category"] not in _NON_TEXT}
    attempts = [article["extensions"]["mf:layout"]["headline"]["attempts"]
                for article in articles.values() if article.get("extensions", {}).get("mf:layout", {}).get("headline")]
    if parameters["layout_rejected_candidates"]["headline"] != sum(attempt - 1 for attempt in attempts):
        errors.append("layout: headline rejection count differs from successful attempt")
    planned_rules = list(plan["zone_rules"])
    for zone in zones.values():
        for index in range(1, len(zone["columns"])):
            center = (zone["columns"][index - 1][1] + zone["columns"][index][0]) / 2
            top = zone["bbox"][1]
            if zone["headline_reserved"] and index < zone["headline_span"]:
                top = zone["headline_reserved"][3]
            planned_rules.append([center - 1, top, center + 1, zone["bbox"][3]])
    for rect in planned_rules:
        matches = [rid for rid, polygon in rules.items() if polygon.hausdorff_distance(box(*rect)) <= TOLERANCE]
        if len(matches) != 1 or any(rid in boxed_rules for rid in matches):
            errors.append("layout: planned zone/column rule requires one distinct actual separator")
    for rid, polygon in rules.items():
        for bid, content in text.items():
            if polygon.intersection(content).area > _LAYOUT_RULE_TEXT_AREA_TOLERANCE:
                errors.append(f"layout {rid}/{bid}: rule intersects textual polygon (>0.5 px²)")
    return errors


def _load_layout_context(root: Path, manifest: dict, assets: dict):
    """Read only the declared template/config of a v2 lot, never excluded texts."""
    if manifest["profile"] != LAYOUT_PROFILE:
        issues = ["layout: template_press_v2 is reserved for the v2 dataset profile"] if "template_press_v2" in assets else []
        return None, issues
    try:
        from .layout import DEFAULT_OPTIONS, check_options

        config = load_json(safe_path(root, manifest["config"]["path"]))["render"]
        if config.get("layout_profile") != LAYOUT_PROFILE or config.get("degradation_profile") is None:
            return None, ["layout: explicit layout and degradation profiles required in config"]
        template = assets["template_press_v2"]
        if template["kind"] != "template":
            return None, ["layout: template_press_v2 must be a template asset"]
        content = load_json(safe_path(root, template["path"]))
        if (content.get("id") != "template_press_v2" or content.get("profile") != LAYOUT_PROFILE
                or content.get("version") != "0.3.0" or content.get("calibrated") is not False):
            return None, ["layout: wrong template identity/profile/version or calibrated claim"]
        if [content.get("heading"), content.get("subtitle")] != template["metadata"].get("literal_text"):
            return None, ["layout: template literal text differs from its registry metadata"]
        options = check_options(content["layout_options"])
        if options != DEFAULT_OPTIONS:
            return None, ["layout: named v2 preset version 1 requires exact DEFAULT_OPTIONS"]
        regular = [asset for asset in assets.values() if asset["kind"] == "font"
                   and Path(asset["path"]).name == "OldStandard-Regular.ttf"]
        if len(regular) != 1:
            return None, ["layout: one declared OldStandard-Regular.ttf required for typography"]
        return {"config": config, "options": options, "font": regular[0], "assets": assets}, []
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        return None, [f"layout: invalid template/config context: {exc}"]


def _layout_template_errors(root: Path, page: dict, template: dict, context: dict) -> list[str]:
    """Bind declared plan/font choices to the copied template and exact font metrics."""
    from PIL import ImageFont
    from .layout import small_body_size

    errors = []
    if template["id"] != "template_press_v2":
        return ["layout: page must reference template_press_v2"]
    parameters = page["provenance"]["parameters"]
    plan, options, config = parameters["layout"], context["options"], context["config"]
    for key in ("width", "height"):
        if config.get(key) != plan[key]:
            errors.append(f"layout: plan {key} differs from config")
    main_count = len(plan["zones"][0]["columns"])
    if config.get("columns") is not None and config["columns"] != main_count:
        errors.append("layout: main column count differs from explicit config.columns")
    for zone in plan["zones"]:
        name, count = zone["id"], len(zone["columns"])
        choices = options["main_columns" if name == "main" else "rez_de_chaussee_columns"]["choice"]
        if count not in choices:
            errors.append(f"layout {name}: column count absent from template options")
        span = zone["headline_span"]
        if span is not None and span not in {min(value, count - 1) for value in options["headline_span"]["choice"]}:
            errors.append(f"layout {name}: headline span absent from template choices")
        metrics = parameters["layout_typography"][name]
        normal, small = metrics["normal_body_size"], metrics["small_body_size"]
        if small != small_body_size(normal, options["small_body_ratio"]):
            errors.append(f"layout {name}: small body differs from template ratio")
        try:
            for suffix, size in (("normal", normal), ("small", small)):
                font = ImageFont.truetype(str(safe_path(root, context["font"]["path"])),
                                         size=size, layout_engine=ImageFont.Layout.BASIC)
                ascent, descent = font.getmetrics()
                expected = max(size * 1.14, (ascent + descent) * 0.92)
                band = zone["headline_body_band"]
                if suffix == "normal" and band is not None and zone["bbox"][3] - band[3] + _LAYOUT_EPSILON < max(expected, ascent + descent):
                    errors.append(f"layout {name}: body band leaves less than one normal font line")
                if not _layout_close(metrics[f"line_spacing_{suffix}"], expected):
                    errors.append(f"layout {name}: {suffix} interline differs from font metrics")
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"layout {name}: cannot verify font metrics: {exc}")
    has_lower = len(plan["zones"]) == 2
    probability = options["rez_de_chaussee_probability"]
    if (probability == 0 and has_lower) or (probability == 1 and not has_lower):
        errors.append("layout: lower zone contradicts template probability endpoint")
    if has_lower:
        share = plan["rez_de_chaussee_share"]
        lo, hi = options["rez_de_chaussee_share"]
        if not lo <= share <= hi:
            errors.append("layout: lower zone share outside template interval")
        gap = plan["zones"][1]["bbox"][1] - plan["zones"][0]["bbox"][3]
        if not _layout_close(gap, options["zone_gap_px"]):
            errors.append("layout: zone gap differs from template")
    has_headline = plan["zones"][0]["headline_span"] is not None
    probability = options["headline_probability"]
    if (probability == 0 and has_headline) or (probability == 1 and main_count >= 3 and not has_headline):
        errors.append("layout: headline contradicts template probability endpoint")
    blocks = {block["id"]: block for block in page["blocks"]}
    lines = {line["id"]: line for line in page["lines"]}
    articles = {article["id"]: article for article in page["articles"]}
    for span in page["provenance"]["text_spans"]:
        asset = context["assets"].get(span["asset_id"], {})
        role = asset.get("metadata", {}).get("role")
        article = articles[span["article_id"]]
        meta = article.get("extensions", {}).get("mf:layout")
        if meta is None:
            continue
        for bid in span["block_ids"]:
            size = meta["body_font_size"]
            if role == "title":
                multiplier = 2 if meta["headline"] and bid == meta["headline"]["block_id"] else 1.25
                size = max(12, round(size * multiplier))
            elif role not in {"body", "advertisement"}:
                errors.append(f"layout {bid}: source role must identify title/body/advertisement")
                continue
            for lid in blocks[bid]["line_ids"]:
                font = lines[lid].get("extensions", {}).get("mf:font", {})
                actual_asset = context["assets"].get(font.get("asset_id"), {})
                expected_name = "OldStandard-Bold.ttf" if role == "title" else "OldStandard-Regular.ttf"
                if (font.get("size") != size or actual_asset.get("kind") != "font"
                        or Path(actual_asset.get("path", "")).name != expected_name):
                    errors.append(f"layout {lid}: font/size disagrees with source role and article typography")
    for article in page["articles"]:
        meta = article.get("extensions", {}).get("mf:layout")
        if meta is None:
            continue
        role = "advertisement" if all(blocks[bid]["category"] == "annonce" for bid in article["block_ids"]) else "body"
        probability = options["small_body_probability"][role]
        if (probability == 0 and meta["small_body_requested"]) or (probability == 1 and not meta["small_body_requested"]):
            errors.append(f"layout {article['id']}: small-body request contradicts template endpoint")
        if role == "advertisement":
            probability = options["boxed_ad_probability"]
            if (probability == 0 and meta["box"] is not None) or (probability == 1 and meta["box"] is None):
                errors.append(f"layout {article['id']}: box contradicts template probability endpoint")
        if meta["box"]:
            lo, hi = options["box_padding_px"]
            if not lo <= meta["box"]["padding"] <= hi:
                errors.append(f"layout {article['id']}: box padding outside template interval")
    return errors
