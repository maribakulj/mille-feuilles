"""Pure PAGE 2019 projection for the local ``page-newseye-v1`` profile.

The rules are those of tests/fixtures/newseye/SPEC.md (revision 3.1): one
top-level TextRegion per textual block, structure on lines in the custom
grammar ``name {key:value;}``, reading order over TextRegions only, and each
advertisement paired with a sibling AdvertRegion of identical Coords. The
function never reads images or writes files; refusals raise before any output.
This is not a general NewsEye or Transkribus exporter.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path, PurePosixPath

from lxml import etree as ET
from shapely.geometry import Polygon

from .exports import PAGE_NS, XSI_NS, _rounded, _schema

PROFILE = "page-newseye-v1"
REPORT_FORMAT = "mille-feuilles-newseye-report"
REPORT_VERSION = "2"  # must equal properties.version.const of the report schema
ORDER_ID = "mf_newseye_order"
EPOCH = "1970-01-01T00:00:00Z"
COMMENTS = "Synthetic composition. Projection page-newseye-v1; fixed dates are reproducibility sentinels."
SCHEMA_LOCATION = (
    f"{PAGE_NS} https://www.primaresearch.org/schema/PAGE/gts/pagecontent/2019-07-15/pagecontent.xsd"
)
_ID = re.compile(r"[A-Za-z0-9_.-]+")
_STRUCTURE = {"titre": ("heading", "heading"), "texte": ("paragraph", "paragraph"),
              "annonce": ("paragraph", "paragraph"), "autre": ("paragraph", "paragraph"),
              "legende": ("caption", "caption")}
_NONTEXT = {"separateur": ("SeparatorRegion", "s"), "illustration": ("GraphicRegion", "g")}
_REPORT_SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "newseye-report.schema.json"


class NewsEyeExportError(ValueError):
    """A page this profile refuses to project; ``code`` names the reason."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@lru_cache(maxsize=1)
def report_constants() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """not_represented and notes, read from the contractual report schema."""
    schema = json.loads(_REPORT_SCHEMA.read_text(encoding="utf-8"))
    properties = schema["properties"]
    return tuple(properties["not_represented"]["const"]), tuple(properties["notes"]["const"])


def _identifier(value, label: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise NewsEyeExportError("custom_value", f"identifiant hors [A-Za-z0-9_.-]+ pour {label} : {value!r}")
    return value


def _image_filename(page: dict, image_filename) -> str:
    value = page["image"]["path"] if image_filename is None else image_filename
    # Same rule as the independent reader: any colon (URI schemes, drive letters) and every
    # control character U+0000..U+001F or U+007F are refused, as are absolute paths and
    # empty, "." or ".." segments.
    if (
        not isinstance(value, str) or not value or value.startswith("/") or "\\" in value or ":" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or any(p in ("", ".", "..") for p in value.split("/")) or PurePosixPath(value).is_absolute()
    ):
        raise NewsEyeExportError("image_filename", f"chemin POSIX relatif sûr attendu : {value!r}")
    return value


def _points(points, page, *, polygon=True) -> str:
    try:
        rounded = _rounded(points, page, polygon=polygon)
    except ValueError as exc:
        raise NewsEyeExportError("geometry", str(exc)) from exc
    return " ".join(f"{x},{y}" for x, y in rounded)


def _node(parent, name: str, **attrs):
    return ET.SubElement(parent, f"{{{PAGE_NS}}}{name}", {k: str(v) for k, v in attrs.items()})


def _text(parent, value: str) -> None:
    _node(_node(parent, "TextEquiv"), "Unicode").text = value


def _check_page(page: dict) -> None:
    if page.get("language") != "fr":
        raise NewsEyeExportError("language", "ce profil n'accepte que fr")
    blocks = {b["id"]: b for b in page["blocks"]}
    order, unordered = page["reading_order"]["block_ids"], page["reading_order"]["unordered_block_ids"]
    for bid in order:
        block = blocks.get(bid)
        if block is None or block["category"] in _NONTEXT:
            raise NewsEyeExportError("reading_order", f"bloc ordonné absent ou non textuel : {bid}")
        if block["category"] == "tableau":
            raise NewsEyeExportError("table_block", f"catégorie tableau hors de ce profil : {bid}")
        if block["category"] not in _STRUCTURE:
            raise NewsEyeExportError("category", f"catégorie inconnue : {block['category']}")
        if block["article_id"] is None:
            raise NewsEyeExportError("free_text_block", f"bloc textuel sans article : {bid}")
        _identifier(block["article_id"], f"article de {bid}")
    for bid in unordered:
        if bid not in blocks or blocks[bid]["category"] not in _NONTEXT:
            raise NewsEyeExportError("reading_order", f"bloc non ordonné absent ou textuel : {bid}")
    if set(order) | set(unordered) != set(blocks) or len(set(order)) != len(order):
        raise NewsEyeExportError("reading_order", "les blocs de l'ordre ne couvrent pas exactement la page")
    for collection in ("blocks", "lines", "words"):
        for item in page[collection]:
            _identifier(item["id"], collection)


def _check_adverts(text_polygons: dict[str, str], advert_ids: list[str]) -> None:
    """Refuse any positive-area overlap between an AdvertRegion and another TextRegion."""
    def polygon(points: str) -> Polygon:
        return Polygon([tuple(int(v) for v in p.split(",")) for p in points.split()])

    for bid in advert_ids:
        advert = polygon(text_polygons[bid])
        for other, points in text_polygons.items():
            if other != bid and advert.intersection(polygon(points)).area > 0:
                raise NewsEyeExportError("advert_overlap", f"l'annonce {bid} chevauche {other}")


def project_page(page: dict, *, image_filename: str | None = None) -> tuple[bytes, dict]:
    """Return (PAGE XML bytes, report) for a validated canonical page; never writes files."""
    _check_page(page)
    filename = _image_filename(page, image_filename)
    blocks = {b["id"]: b for b in page["blocks"]}
    lines = {line["id"]: line for line in page["lines"]}
    words = {w["id"]: w for w in page["words"]}
    order, unordered = page["reading_order"]["block_ids"], page["reading_order"]["unordered_block_ids"]

    # Geometry first: every refusal happens before any element is emitted.
    text_polygons = {bid: _points(blocks[bid]["polygon"], page) for bid in order}
    _check_adverts(text_polygons, [bid for bid in order if blocks[bid]["category"] == "annonce"])

    root = ET.Element(f"{{{PAGE_NS}}}PcGts", nsmap={None: PAGE_NS, "xsi": XSI_NS})
    root.set(f"{{{XSI_NS}}}schemaLocation", SCHEMA_LOCATION)
    root.set("pcGtsId", f"p_{_identifier(page['page_id'], 'page')}")
    metadata = _node(root, "Metadata")
    _node(metadata, "Creator").text = "Mille Feuilles"
    _node(metadata, "Created").text = EPOCH
    _node(metadata, "LastChange").text = EPOCH
    _node(metadata, "Comments").text = COMMENTS
    element = _node(root, "Page", imageFilename=filename, imageWidth=page["image"]["width"],
                    imageHeight=page["image"]["height"], primaryLanguage="French")
    if order:
        group = _node(_node(element, "ReadingOrder"), "OrderedGroup", id=ORDER_ID)
        for index, bid in enumerate(order):
            _node(group, "RegionRefIndexed", index=index, regionRef=f"r_{bid}")

    mapping = {}
    for index, bid in enumerate(order):
        block = blocks[bid]
        region_type, structure = _STRUCTURE[block["category"]]
        region = _node(element, "TextRegion", id=f"r_{bid}", type=region_type,
                       custom=f"readingOrder {{index:{index};}} structure {{type:{structure};}}")
        mapping[f"r_{bid}"] = bid
        _node(region, "Coords", points=text_polygons[bid])
        texts = []
        for line_index, lid in enumerate(block["line_ids"]):
            line = lines[lid]
            if not line["word_ids"]:
                raise NewsEyeExportError("empty_line", f"ligne sans mot : {lid}")
            line_elem = _node(region, "TextLine", id=f"l_{lid}",
                              custom=f"readingOrder {{index:{line_index};}} "
                                     f"structure {{id:{block['article_id']}; type:article;}}")
            mapping[f"l_{lid}"] = lid
            _node(line_elem, "Coords", points=_points(line["polygon"], page))
            _node(line_elem, "Baseline", points=_points(line["baseline"], page, polygon=False))
            for wid in line["word_ids"]:
                word = words[wid]
                word_elem = _node(line_elem, "Word", id=f"w_{wid}")
                mapping[f"w_{wid}"] = wid
                _node(word_elem, "Coords", points=_points(word["polygon"], page))
                _text(word_elem, word["text"])
            _text(line_elem, line["text"])
            texts.append(line["text"])
        _text(region, "\n".join(texts))
        if block["category"] == "annonce":
            advert = _node(element, "AdvertRegion", id=f"a_{bid}")
            _node(advert, "Coords", points=text_polygons[bid])
            mapping[f"a_{bid}"] = bid
    for bid in unordered:
        block = blocks[bid]
        kind, prefix = _NONTEXT[block["category"]]
        region = _node(element, kind, id=f"{prefix}_{bid}")
        _node(region, "Coords", points=_points(block["polygon"], page))
        mapping[f"{prefix}_{bid}"] = bid

    schema = _schema("page")
    if not schema.validate(root):
        raise NewsEyeExportError("xsd", str(schema.error_log.last_error))
    xml = ET.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    not_represented, notes = report_constants()
    report = {
        "format": REPORT_FORMAT, "version": REPORT_VERSION, "profile": PROFILE,
        "page_id": page["page_id"], "image_filename": filename,
        "id_mapping": dict(sorted(mapping.items())),
        "not_represented": list(not_represented), "notes": list(notes),
    }
    return xml, report
