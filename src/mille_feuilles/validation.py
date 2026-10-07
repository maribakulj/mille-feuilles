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
from PIL import Image
from shapely.geometry import LineString, Polygon

SCHEMA_VERSION = "0.2.0"
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
    pages = []
    for record in manifest["pages"]:
        try:
            page = read(record["path"])
            issues = validate_page(page)
            check(f"page:{record['id']}", issues)
            if issues:
                continue
            page_issues = []
            if any(word["legibility"] != "readable" for word in page["words"]):
                page_issues.append("pilot profile excludes uncertain/illegible word supervision")
            if page["page_id"] != record["id"] or page["profile"] != manifest["profile"]:
                page_issues.append("page identity/profile differs from manifest")
            if page["schema_version"] != manifest["schema_version"]:
                page_issues.append("page schema_version differs from manifest")
            provenance = page["provenance"]
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
