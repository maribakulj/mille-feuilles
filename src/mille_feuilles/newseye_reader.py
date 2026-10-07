"""Independent, strict reader for the local PAGE ``page-newseye-v1`` profile.

Implemented from the frozen NewsEye specification (revision 3.1), not from an
exporter. This is not a general PAGE, NewsEye or Transkribus reader. Geometry is
observed from XML; no image, schema, DTD, network resource or corpus is read.
"""

from __future__ import annotations

import math
import re
import unicodedata
from pathlib import PurePosixPath

from lxml import etree
from shapely.errors import ShapelyError
from shapely.geometry import Polygon

PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"
_ID = re.compile(r"[A-Za-z0-9_.-]+")
_DECIMAL = re.compile(r"[0-9]+")
_REGION_CUSTOM = re.compile(
    r"readingOrder \{index:([0-9]+);\} structure \{type:(heading|paragraph|caption);\}"
)
_LINE_CUSTOM = re.compile(
    r"readingOrder \{index:([0-9]+);\} structure \{id:([A-Za-z0-9_.-]+); type:article;\}"
)
_REGIONS = {"TextRegion", "AdvertRegion", "SeparatorRegion", "GraphicRegion"}
# GEOS coordinates use doubles. Reject integers outside their exact domain.
_MAX_INTEGER = 2**53 - 1


class NewsEyeReadError(ValueError):
    """Controlled refusal, with a stable category and optional observations."""

    def __init__(self, code: str, message: str, *, details: dict | None = None):
        self.code = code
        self.details = {} if details is None else details
        super().__init__(f"{code}: {message}")


class _NoExternalResources(etree.Resolver):
    def resolve(self, url, public_id, context):
        raise NewsEyeReadError("xml_external_resource", "External XML resources are forbidden")


def _q(name: str) -> str:
    return f"{{{PAGE_NS}}}{name}"


def _inspect(element, *, attrs=(), required=(), children=(), text=False):
    if set(element.attrib) - set(attrs) or set(required) - set(element.attrib):
        raise NewsEyeReadError("structure", f"Unexpected or missing attributes on {element.tag}")
    allowed = {_q(name) for name in children}
    if any(child.tag not in allowed for child in element):
        raise NewsEyeReadError("structure", f"Unexpected child of {element.tag}")
    if not text and element.text and element.text.strip():
        raise NewsEyeReadError("structure", "Mixed XML content is forbidden")
    if any(child.tail and child.tail.strip() for child in element):
        raise NewsEyeReadError("structure", "Mixed XML content is forbidden")


def _one(element, name):
    matches = element.findall(_q(name))
    if len(matches) != 1:
        raise NewsEyeReadError("structure", f"Expected exactly one direct {name}")
    return matches[0]


def _integer(value: str | None, *, code="geometry", positive=False):
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
        raise NewsEyeReadError(code, "Expected an unsigned decimal integer")
    # Bound before int(), including a potentially hostile thousands-digit value.
    significant = value.lstrip("0") or "0"
    if len(significant) > 16:
        raise NewsEyeReadError(code, "Integer exceeds the exact coordinate domain")
    number = int(significant)
    if number > _MAX_INTEGER or (positive and number == 0):
        raise NewsEyeReadError(code, "Integer is outside the permitted domain")
    return number


def _points(element, name, width, height, *, baseline=False):
    node = _one(element, name)
    _inspect(node, attrs=("points",), required=("points",))
    points = []
    for token in node.attrib["points"].split():
        pair = token.split(",")
        if len(pair) != 2:
            raise NewsEyeReadError("geometry", "Each point must have two coordinates")
        x, y = (_integer(value) for value in pair)
        if x > width or y > height:
            raise NewsEyeReadError("geometry", "Coordinate outside the page dimensions")
        points.append([x, y])
    minimum = 2 if baseline else 3
    if len({tuple(point) for point in points}) < minimum:
        raise NewsEyeReadError("geometry", f"Expected at least {minimum} distinct points")
    if not baseline:
        try:
            polygon = Polygon(points)
            if not polygon.is_valid or not math.isfinite(polygon.area) or polygon.area <= 0:
                raise NewsEyeReadError("geometry", "Invalid or zero-area polygon")
        except ShapelyError as exc:
            raise NewsEyeReadError("geometry", "Polygon could not be interpreted") from exc
    return points


def _text(element):
    equiv = _one(element, "TextEquiv")
    _inspect(equiv, children=("Unicode",))
    unicode = _one(equiv, "Unicode")
    _inspect(unicode, text=True)
    value = unicode.text or ""
    if not value or unicodedata.normalize("NFC", value) != value:
        raise NewsEyeReadError("text", "Expected nonempty NFC text, without normalization")
    return value


def _custom(element, *, line=False):
    expression = _LINE_CUSTOM if line else _REGION_CUSTOM
    match = expression.fullmatch(element.get("custom", ""))
    if match is None:
        raise NewsEyeReadError("custom", "Invalid or missing complete custom grammar")
    return _integer(match[1], code="reading_order"), match[2]


def _contiguous(indices):
    if sorted(indices) != list(range(len(indices))):
        raise NewsEyeReadError("reading_order", "Indices must be unique and contiguous from zero")


def _image(page):
    width = _integer(page.get("imageWidth"), positive=True)
    height = _integer(page.get("imageHeight"), positive=True)
    filename = page.get("imageFilename", "")
    path = PurePosixPath(filename)
    if (
        not filename
        or filename.startswith("/")
        or "\\" in filename
        or ":" in filename
        or any(part in {"", ".", ".."} for part in filename.split("/"))
        or any(ord(char) < 32 or ord(char) == 127 for char in filename)
        or path.is_absolute()
    ):
        raise NewsEyeReadError("image_path", "imageFilename must be a safe relative POSIX path")
    if page.get("primaryLanguage") != "French":
        raise NewsEyeReadError("language", "This profile requires primaryLanguage French")
    return {"filename": filename, "width": width, "height": height}


def _parse(xml):
    if not isinstance(xml, bytes):
        raise NewsEyeReadError("input", "read_page requires bytes")
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        recover=False,
        remove_comments=True,
        remove_pis=True,
    )
    parser.resolvers.add(_NoExternalResources())
    try:
        root = etree.fromstring(xml, parser)
    except (etree.XMLSyntaxError, ValueError) as exc:
        if isinstance(exc, NewsEyeReadError):
            raise
        raise NewsEyeReadError("xml", "Malformed or unsafe XML") from exc
    if root.getroottree().docinfo.doctype:
        raise NewsEyeReadError("dtd", "DTDs and declared entities are forbidden")
    if root.tag != _q("PcGts"):
        raise NewsEyeReadError("structure", "Expected PAGE 2019 PcGts root")
    seen = set()
    for node in root.iter():
        for attr in ("id", "pcGtsId"):
            if attr not in node.attrib:
                continue
            identifier = node.attrib[attr]
            if not _ID.fullmatch(identifier) or identifier in seen:
                raise NewsEyeReadError("id", "XML identifiers must be valid and globally unique")
            seen.add(identifier)
    return root


def _read_text_region(region, width, height, geometry, word_ids_by_line):
    _inspect(
        region,
        attrs=("id", "type", "custom"),
        required=("id", "type", "custom"),
        children=("Coords", "TextLine", "TextEquiv"),
    )
    index, structure = _custom(region)
    if region.attrib["type"] != structure:
        raise NewsEyeReadError("custom", "Region type contradicts custom structure type")
    lines = []
    for line in region.findall(_q("TextLine")):
        _inspect(
            line,
            attrs=("id", "custom"),
            required=("id", "custom"),
            children=("Coords", "Baseline", "Word", "TextEquiv"),
        )
        line_index, article = _custom(line, line=True)
        line_id = line.attrib["id"]
        geometry["lines"][line_id] = [
            _points(line, "Coords", width, height),
            _points(line, "Baseline", width, height, baseline=True),
        ]
        words = []
        word_ids_by_line[line_id] = []
        for word in line.findall(_q("Word")):
            _inspect(word, attrs=("id",), required=("id",), children=("Coords", "TextEquiv"))
            word_id, word_text = word.attrib["id"], _text(word)
            if word_text.split() != [word_text]:
                raise NewsEyeReadError("text", "A Word must contain exactly one token")
            geometry["words"][word_id] = [word_text, _points(word, "Coords", width, height)]
            words.append(word_text)
            word_ids_by_line[line_id].append(word_id)
        text = _text(line)
        # Preserve all original whitespace; only compare the observed token sequence.
        if not words or text.split() != words:
            raise NewsEyeReadError("text", "Words contradict the line's token sequence")
        lines.append((line_index, [line_id, article, text]))
    if not lines:
        raise NewsEyeReadError("structure", "A TextRegion must have direct TextLine children")
    _contiguous([index for index, _ in lines])
    observed_lines = [observation for _, observation in sorted(lines)]
    if _text(region) != "\n".join(line[2] for line in observed_lines):
        raise NewsEyeReadError("text", "Region text contradicts its ordered direct lines")
    return index, {"id": region.attrib["id"], "structure": structure, "lines": observed_lines}


def read_page(xml: bytes) -> dict:
    """Read bytes without I/O; reject malformed or ambiguous profile structure.

    Return ``reading``, ``image``, ``geometry``, ``word_ids_by_line`` and
    ``region_types``. The first
    and third match the independent golden observations, with their descriptive
    ``format`` / ``version`` / ``note`` excluded. Every point and exact Unicode
    string is retained. Only reading-order indices determine text-region and
    line order; word order is the direct XML child order. Nontext separator IDs
    are a sorted set, since this profile does not preserve nontext reading order.
    Every line has at least one Word, as required by the complete local profile.
    Region XML types remain observable even when an AdvertRegion covers no text.

    Refusals use NewsEyeReadError.code: input, xml, xml_external_resource, dtd,
    structure, id, custom, reading_order, reference, omitted_text_regions,
    geometry, text, image_path or language. Omission details include the IDs.
    """
    root = _parse(xml)
    _inspect(
        root,
        attrs=("pcGtsId", f"{{{_XSI}}}schemaLocation"),
        required=("pcGtsId",),
        children=("Metadata", "Page"),
    )
    metadata = _one(root, "Metadata")
    metadata_names = ("Creator", "Created", "LastChange", "Comments")
    _inspect(metadata, children=metadata_names)
    for name in metadata_names:
        _inspect(_one(metadata, name), text=True)
    page = _one(root, "Page")
    page_attrs = ("imageFilename", "imageWidth", "imageHeight", "primaryLanguage")
    _inspect(page, attrs=page_attrs, required=page_attrs, children=(*_REGIONS, "ReadingOrder"))
    image = _image(page)
    width, height = image["width"], image["height"]
    geometry = {"regions": {}, "lines": {}, "words": {}}
    word_ids_by_line, text_regions, region_indices, polygons = {}, {}, {}, {}
    region_types = {}
    adverts, separators = [], []
    for region in page:
        if region.tag == _q("ReadingOrder"):
            continue
        if region.tag != _q("TextRegion"):
            _inspect(region, attrs=("id",), required=("id",), children=("Coords",))
        elif "id" not in region.attrib:
            raise NewsEyeReadError("structure", "TextRegion requires an id")
        identifier = region.attrib["id"]
        region_types[identifier] = etree.QName(region).localname
        points = _points(region, "Coords", width, height)
        geometry["regions"][identifier] = points
        polygons[identifier] = Polygon(points)
        if region.tag == _q("TextRegion"):
            index, observation = _read_text_region(
                region, width, height, geometry, word_ids_by_line
            )
            region_indices[identifier], text_regions[identifier] = index, observation
        elif region.tag == _q("AdvertRegion"):
            adverts.append(identifier)
        elif region.tag == _q("SeparatorRegion"):
            separators.append(identifier)

    order = _one(page, "ReadingOrder")
    _inspect(order, children=("OrderedGroup",))
    group = _one(order, "OrderedGroup")
    _inspect(group, attrs=("id",), required=("id",), children=("RegionRefIndexed",))
    references, targets = [], set()
    for reference in group:
        _inspect(reference, attrs=("index", "regionRef"), required=("index", "regionRef"))
        index = _integer(reference.attrib["index"], code="reading_order")
        target = reference.attrib["regionRef"]
        if target not in text_regions or target in targets:
            raise NewsEyeReadError(
                "reference", "Reference must target a unique top-level TextRegion"
            )
        targets.add(target)
        references.append((index, target))
    omitted = sorted(set(text_regions) - targets)
    if omitted:
        raise NewsEyeReadError(
            "omitted_text_regions",
            "Every top-level TextRegion must be referenced",
            details={"omitted_text_regions": omitted},
        )
    if not references:
        raise NewsEyeReadError("structure", "Expected at least one text-region reference")
    _contiguous([index for index, _ in references])
    for index, target in references:
        if region_indices[target] != index:
            raise NewsEyeReadError("reading_order", "Region custom index contradicts its reference")

    coverages, observed, advert_ranks = {}, [], []
    for rank, target in sorted(references):
        polygon = polygons[target]
        try:
            cover = max(
                (polygon.intersection(polygons[advert]).area / polygon.area for advert in adverts),
                default=0.0,
            )
        except ShapelyError as exc:
            raise NewsEyeReadError("geometry", "Advert coverage could not be measured") from exc
        if not math.isfinite(cover):
            raise NewsEyeReadError("geometry", "Advert coverage is not finite")
        observation = text_regions[target]
        structure = observation["structure"]
        kind = (
            "annonce"
            if cover >= 0.5
            else {"heading": "titre", "caption": "legende"}.get(structure, "texte")
        )
        observation["kind"] = kind
        coverages[target] = cover
        observed.append(observation)
        if kind == "annonce":
            advert_ranks.append(rank)
    return {
        "reading": {
            "text_regions_in_order": observed,
            "advert_cover_max": coverages,
            "advert_ranks": advert_ranks,
            "separators": sorted(separators),
            "omitted_text_regions": [],
        },
        "image": image,
        "geometry": geometry,
        "word_ids_by_line": word_ids_by_line,
        "region_types": region_types,
    }
