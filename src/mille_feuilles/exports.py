"""Deterministic PAGE 2019, ALTO 4.4 and COCO projections of canonical pages.

The canonical JSON is authoritative. See docs/EXPORTS.md for custom metadata,
rounding, and explicitly unrepresented fields. XML validation is offline.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path

from lxml import etree as ET

PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
ALTO_NS = "http://www.loc.gov/standards/alto/ns-v4#"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
CATEGORIES = ("titre", "texte", "legende", "annonce", "tableau", "illustration", "separateur", "autre")
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "xml"
SCHEMAS = {"page": "page-2019-07-15.xsd", "alto": "alto-4-4.xsd"}
EPOCH = "1970-01-01T00:00:00Z"  # required PAGE dates, fixed non-historical sentinel


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _lot_path(root, relative):
    try:
        root = Path(root).resolve()
        path = root / relative
        path.resolve().relative_to(root)
    except RuntimeError as exc:
        raise ValueError("Symlink loop in export path") from exc
    return path


def _page_id(page):
    pid = page["page_id"]
    if not isinstance(pid, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", pid) is None:
        raise ValueError("Invalid canonical page identifier")
    return pid


def _node(parent, local_name, **attrs):
    namespace = ET.QName(parent).namespace
    return ET.SubElement(parent, f"{{{namespace}}}{local_name}", {k: str(v) for k, v in attrs.items()})


def _ids(page):
    return {f"{prefix}_{item['id']}": item["id"]
            for kind, prefix in (("blocks", "b"), ("lines", "l"), ("words", "w"))
            for item in page[kind]}


def _area(points):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2)
               in zip(points, points[1:] + points[:1])) / 2


def _bbox(points):
    xs, ys = zip(*points)
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def _rounded(points, page, polygon=True):
    limits = (page["image"]["width"], page["image"]["height"])
    result = [[min(limit, max(0, math.floor(v + 0.5))) for v, limit in zip(point, limits)] for point in points]
    if polygon and (len(result) < 3 or len(set(map(tuple, result))) != len(result) or _area(result) <= 0):
        raise ValueError("PAGE polygon degenerates after integer rounding")
    if polygon:
        # Rounding may make previously disjoint edges touch or cross.
        def cross(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

        def on_segment(a, b, c):
            return cross(a, b, c) == 0 and min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])

        edges = list(zip(result, result[1:] + result[:1]))
        for i, (a, b) in enumerate(edges):
            for j, (c, d) in enumerate(edges[i + 2:], i + 2):
                if i == 0 and j == len(edges) - 1:
                    continue
                if (cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0) or any((on_segment(a, b, c), on_segment(a, b, d), on_segment(c, d, a), on_segment(c, d, b))):
                    raise ValueError("PAGE polygon degenerates after integer rounding (edge intersection)")
    if not polygon and len(set(map(tuple, result))) < 2:
        raise ValueError("PAGE baseline degenerates after integer rounding")
    return result


def _points(points):
    return " ".join(f"{x},{y}" for x, y in points)


def _parse_points(value):
    points = [[float(v) for v in pair.split(",")] for pair in value.split()]
    if len(points) < 2 or any(len(point) != 2 or not all(math.isfinite(v) for v in point) for point in points):
        raise ValueError("Invalid or nonfinite exported geometry")
    return points


def _page_coords(parent, points, page, name="Coords"):
    return _node(parent, name, points=_points(_rounded(points, page, polygon=name == "Coords")))


def _page_text(parent, text):
    _node(_node(parent, "TextEquiv"), "Unicode").text = text


def _page_region_kind(block):
    return {"annonce": "AdvertRegion", "tableau": "TableRegion",
            "illustration": "GraphicRegion", "separateur": "SeparatorRegion"}.get(block["category"], "TextRegion")


def _build_page(page):
    if page["language"] != "fr":
        raise ValueError("The PAGE language mapping of this profile supports fr only")
    root = ET.Element(f"{{{PAGE_NS}}}PcGts", nsmap={None: PAGE_NS, "xsi": XSI_NS})
    root.set("pcGtsId", f"p_{page['page_id']}")
    root.set(f"{{{XSI_NS}}}schemaLocation", f"{PAGE_NS} https://www.primaresearch.org/schema/PAGE/gts/pagecontent/2019-07-15/pagecontent.xsd")
    metadata = _node(root, "Metadata")
    _node(metadata, "Creator").text = "Mille Feuilles"
    _node(metadata, "Created").text = EPOCH
    _node(metadata, "LastChange").text = EPOCH
    _node(metadata, "Comments").text = "Synthetic composition. Fixed dates are reproducibility sentinels, not source dates."
    ud = _node(metadata, "UserDefined")
    _node(ud, "UserAttribute", name="mille-feuilles:articles", type="xsd:string", value=_json(page["articles"]))
    elem = _node(root, "Page", imageFilename=page["image"]["path"], imageWidth=page["image"]["width"], imageHeight=page["image"]["height"], primaryLanguage="French")
    order = page["reading_order"]
    if order["block_ids"] or order["unordered_block_ids"]:
        ro = _node(elem, "ReadingOrder")
        # One unordered root expresses a total text order plus unrelated graphics.
        group = _node(ro, "UnorderedGroup", id="mf_reading_root")
        if order["block_ids"]:
            ordered = _node(group, "OrderedGroup", id="mf_text_order")
            for index, bid in enumerate(order["block_ids"]):
                _node(ordered, "RegionRefIndexed", index=index, regionRef=f"b_{bid}")
        for bid in order["unordered_block_ids"]:
            _node(group, "RegionRef", regionRef=f"b_{bid}")
    blocks = {b["id"]: b for b in page["blocks"]}
    lines = {line["id"]: line for line in page["lines"]}
    words = {word["id"]: word for word in page["words"]}
    for bid in order["block_ids"] + order["unordered_block_ids"]:
        block = blocks[bid]
        region = _node(elem, _page_region_kind(block), id=f"b_{bid}", custom=_json({"category": block["category"], "article_id": block["article_id"]}))
        _page_coords(region, block["polygon"], page)
        content = region
        if block["line_ids"] and _page_region_kind(block) != "TextRegion":
            content = _node(region, "TextRegion", id=f"c_{bid}", type="other")
            _page_coords(content, block["polygon"], page)
        if ET.QName(content).localname == "TextRegion":
            content.set("type", {"titre": "heading", "texte": "paragraph", "legende": "caption"}.get(block["category"], "other"))
        for index, lid in enumerate(block["line_ids"]):
            line = lines[lid]
            line_elem = _node(content, "TextLine", id=f"l_{lid}", index=index, custom=_json({"legibility": line["legibility"]}))
            _page_coords(line_elem, line["polygon"], page)
            _page_coords(line_elem, line["baseline"], page, "Baseline")
            for wid in line["word_ids"]:
                word = words[wid]
                word_elem = _node(line_elem, "Word", id=f"w_{wid}", custom=_json({key: word[key] for key in ("char_span", "legibility", "hyphenation")}))
                _page_coords(word_elem, word["polygon"], page)
                _page_text(word_elem, word["text"])
            _page_text(line_elem, line["text"])
        if block["line_ids"]:
            _page_text(content, "\n".join(lines[lid]["text"] for lid in block["line_ids"]))
    return root


def _alto_shape(parent, polygon):
    x, y, width, height = _bbox(polygon)
    for key, value in zip(("HPOS", "VPOS", "WIDTH", "HEIGHT"), (x, y, width, height)):
        parent.set(key, str(value))
    _node(_node(parent, "Shape"), "Polygon", POINTS=_points(polygon))


def _alto_kind(block):
    return {"illustration": "Illustration", "separateur": "GraphicalElement"}.get(block["category"], "TextBlock")


def _line_gaps(line, words):
    ordered = [words[wid] for wid in line["word_ids"]]
    return [right["char_span"][0] - left["char_span"][1] for left, right in zip(ordered, ordered[1:])]


def _build_alto(page):
    root = ET.Element(f"{{{ALTO_NS}}}alto", SCHEMAVERSION="4.4", nsmap={None: ALTO_NS, "xsi": XSI_NS})
    root.set(f"{{{XSI_NS}}}schemaLocation", f"{ALTO_NS} https://www.loc.gov/standards/alto/v4/alto-4-4.xsd")
    desc = _node(root, "Description")
    _node(desc, "MeasurementUnit").text = "pixel"
    _node(_node(desc, "sourceImageInformation"), "fileName").text = page["image"]["path"]
    tags = _node(root, "Tags")
    for category in CATEGORIES:
        _node(tags, "LayoutTag", ID=f"category_{category}", TYPE="mille-feuilles:category", LABEL=category)
    for legibility in ("readable", "uncertain", "illegible"):
        _node(tags, "OtherTag", ID=f"legibility_{legibility}", TYPE="mille-feuilles:legibility", LABEL=legibility)
    for article in page["articles"]:
        _node(tags, "StructureTag", ID=f"a_{article['id']}", TYPE="mille-feuilles:article", LABEL=article["id"], DESCRIPTION=_json({"block_ids": article["block_ids"]}))
    hyphenation_groups = {}
    for word in page["words"]:
        hyp = word["hyphenation"]
        if hyp:
            hyphenation_groups[hyp["group_id"]] = hyp["reconstructed_text"]
    for gid, text in sorted(hyphenation_groups.items()):
        _node(tags, "OtherTag", ID=f"h_{gid}", TYPE="mille-feuilles:hyphenation", LABEL=gid, DESCRIPTION=text)
    words = {w["id"]: w for w in page["words"]}
    for line in page["lines"]:
        gaps = _line_gaps(line, words)
        if any(g != 1 for g in gaps):
            _node(tags, "OtherTag", ID=f"s_{line['id']}", TYPE="mille-feuilles:spaces", LABEL=line["id"], DESCRIPTION=_json(gaps))
    order = page["reading_order"]
    if order["block_ids"] or order["unordered_block_ids"]:
        ro = _node(root, "ReadingOrder")
        for key, kind, gid in (("block_ids", "OrderedGroup", "mf_text_order"), ("unordered_block_ids", "UnorderedGroup", "mf_unordered")):
            if order[key]:
                group = _node(ro, kind, ID=gid)
                for bid in order[key]:
                    _node(group, "ElementRef", ID=f"r_{bid}", REF=f"b_{bid}")
    elem = _node(_node(root, "Layout"), "Page", ID=f"p_{page['page_id']}", WIDTH=page["image"]["width"], HEIGHT=page["image"]["height"], PHYSICAL_IMG_NR=1, LANG=page["language"])
    space = _node(elem, "PrintSpace", HPOS=0, VPOS=0, WIDTH=page["image"]["width"], HEIGHT=page["image"]["height"])
    blocks = {b["id"]: b for b in page["blocks"]}
    lines = {line["id"]: line for line in page["lines"]}
    for bid in order["block_ids"] + order["unordered_block_ids"]:
        block = blocks[bid]
        tagrefs = [f"category_{block['category']}"]
        if block["article_id"] is not None:
            tagrefs.append(f"a_{block['article_id']}")
        block_elem = _node(space, _alto_kind(block), ID=f"b_{bid}", TAGREFS=" ".join(tagrefs))
        _alto_shape(block_elem, block["polygon"])
        for lid in block["line_ids"]:
            line = lines[lid]
            if not line["word_ids"]:
                raise ValueError("ALTO cannot represent an empty TextLine in the selected profile")
            gaps = _line_gaps(line, words)
            refs = [f"legibility_{line['legibility']}"]
            if any(g != 1 for g in gaps):
                refs.append(f"s_{lid}")
            line_elem = _node(block_elem, "TextLine", ID=f"l_{lid}", BASELINE=_points(line["baseline"]), TAGREFS=" ".join(refs))
            _alto_shape(line_elem, line["polygon"])
            for index, wid in enumerate(line["word_ids"]):
                word = words[wid]
                refs = [f"legibility_{word['legibility']}"]
                hyp = word["hyphenation"]
                if hyp:
                    refs.append(f"h_{hyp['group_id']}")
                word_elem = _node(line_elem, "String", ID=f"w_{wid}", CONTENT=word["text"], TAGREFS=" ".join(refs))
                if hyp:
                    word_elem.set("SUBS_TYPE", "HypPart1" if hyp["part"] == "start" else "HypPart2")
                    word_elem.set("SUBS_CONTENT", hyp["reconstructed_text"])
                _alto_shape(word_elem, word["polygon"])
                if index < len(gaps) and gaps[index] > 0:
                    _node(line_elem, "SP")
    return root


class _LocalSchemas(ET.Resolver):
    def resolve(self, url, pubid, context):
        if url in ("http://www.loc.gov/standards/xlink/xlink.xsd", "https://www.loc.gov/standards/xlink/xlink.xsd"):
            return self.resolve_filename(str(SCHEMA_DIR / "xlink.xsd"), context)
        if "://" in url:
            raise OSError(f"Unarchived external XML schema: {url}")
        return None


def _parser():
    parser = ET.XMLParser(resolve_entities=False, no_network=True)
    parser.resolvers.add(_LocalSchemas())
    return parser


@lru_cache(maxsize=2)
def _schema(kind):
    return ET.XMLSchema(ET.parse(str(SCHEMA_DIR / SCHEMAS[kind]), _parser()))


def _export_report(page, paths):
    """The required sidecar contract, independent of any manifest hash."""
    return {
        "schema_version": "0.2.0", "page_id": page["page_id"],
        "canonical_path": f"pages/{page['page_id']}.json", "paths": dict(paths),
        "id_mapping": _ids(page),
        "page_container_mapping": {f"c_{b['id']}": b["id"] for b in page["blocks"] if b["line_ids"] and _page_region_kind(b) != "TextRegion"},
        "articles": page["articles"],
        "schemas": {kind: {"path": SCHEMAS[kind], "sha256": hashlib.sha256((SCHEMA_DIR / SCHEMAS[kind]).read_bytes()).hexdigest()} for kind in SCHEMAS},
        "not_represented": {
            "page": ["provenance", "transforms", "image.sha256", "image.color_mode", "image.dpi", "profile", "extensions", "subpixel geometry (integer rounding, <= 0.5 px per coordinate)"],
            "alto": ["provenance", "transforms", "image.sha256", "image.color_mode", "image.dpi", "profile", "extensions"],
            "coco": ["articles", "reading_order", "lines", "words", "language", "provenance", "transforms", "image.sha256", "image.color_mode", "image.dpi", "profile", "extensions"],
        },
        "custom_metadata": {
            "page": "JSON in custom attributes: category, article_id, legibility, char_span, hyphenation; articles in Metadata/UserDefined",
            "alto": "Tags: canonical category, article block order, legibility, hyphenation group; non-single spaces in a line's spaces tag",
        },
        "notes": ["Keep canonical JSON to preserve all nonprojected data.", "COCO autre stays category 8; Axel OLR mapping autre -> texte belongs to its adapter.", "Image paths resolve from the lot root.", "No implicit geometric sorting; XML serializes canonical reading order.", "PAGE timestamps are fixed 1970-01-01 reproducibility sentinels."],
    }


def export_page(page: dict, out_root: Path) -> dict:
    """Write two XML files and a loss/mapping report; return lot-relative paths."""
    out_root = Path(out_root)
    pid = _page_id(page)
    paths = {kind: f"exports/{kind}/{pid}.xml" for kind in ("page", "alto")}
    roots = {"page": _build_page(page), "alto": _build_alto(page)}
    for kind, root in roots.items():
        _schema(kind).assertValid(root)
        path = _lot_path(out_root, paths[kind])
        path.parent.mkdir(parents=True, exist_ok=True)
        ET.ElementTree(root).write(str(path), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    paths["report"] = f"exports/reports/{page['page_id']}.json"
    _write_json(_lot_path(out_root, paths["report"]), _export_report(page, paths))
    return paths


def export_coco(pages: list[dict], out_root: Path) -> Path:
    """Export blocks only; numeric IDs and canonical mappings are collision-free."""
    images, annotations = [], []
    mapping = {"images": {}, "annotations": {}}
    seen = set()
    for image_id, page in enumerate(pages, 1):
        _page_id(page)
        if page["page_id"] in seen:
            raise ValueError(f"Duplicate page_id: {page['page_id']}")
        seen.add(page["page_id"])
        images.append({"id": image_id, "file_name": page["image"]["path"], "width": page["image"]["width"], "height": page["image"]["height"]})
        mapping["images"][str(image_id)] = page["page_id"]
        for block in page["blocks"]:
            annotation_id = len(annotations) + 1
            area = _area(block["polygon"])
            if area <= 0:
                raise ValueError(f"Non-clockwise or degenerate block polygon: {block['id']}")
            annotations.append({"id": annotation_id, "image_id": image_id, "category_id": CATEGORIES.index(block["category"]) + 1,
                                "segmentation": [[v for point in block["polygon"] for v in point]],
                                "bbox": _bbox(block["polygon"]), "area": area, "iscrowd": 0})
            mapping["annotations"][str(annotation_id)] = {"page_id": page["page_id"], "block_id": block["id"]}
    root = Path(out_root)
    path = _lot_path(root, "exports/coco/instances.json")
    _write_json(path, {"images": images, "annotations": annotations, "categories": [{"id": i, "name": name} for i, name in enumerate(CATEGORIES, 1)], "mille_feuilles_id_mapping": mapping})
    return path


def _page_read(root):
    ns = {"p": PAGE_NS}
    elem = root.find("p:Page", ns)
    articles = json.loads(root.find("p:Metadata/p:UserDefined/p:UserAttribute[@name='mille-feuilles:articles']", ns).get("value"))
    def mapping(xml_id, prefix):
        return xml_id.removeprefix(prefix + "_")

    ro = elem.find("p:ReadingOrder/p:UnorderedGroup", ns)
    ordered, unordered = [], []
    if ro is not None:
        ordered_nodes = ro.findall("p:OrderedGroup/p:RegionRefIndexed", ns)
        if [int(n.get("index")) for n in ordered_nodes] != list(range(len(ordered_nodes))):
            raise ValueError("PAGE reading-order indices are not consecutive")
        ordered = [mapping(n.get("regionRef"), "b") for n in ordered_nodes]
        unordered = [mapping(n.get("regionRef"), "b") for n in ro.findall("p:RegionRef", ns)]
    blocks, lines, words = [], [], []
    for region in elem:
        if not ET.QName(region).localname.endswith("Region"):
            continue
        if not region.get("id", "").startswith("b_"):
            raise ValueError("PAGE region missing canonical identifier prefix")
        bid = mapping(region.get("id"), "b")
        block = {"id": bid, **json.loads(region.get("custom")), "polygon": _parse_points(region.find("p:Coords", ns).get("points")), "line_ids": []}
        if ET.QName(region).localname != _page_region_kind(block):
            raise ValueError(f"PAGE region type differs for {bid}")
        nested = [child for child in region if ET.QName(child).localname.endswith("Region")]
        if nested and (block["category"] not in ("annonce", "tableau") or len(nested) != 1 or ET.QName(nested[0]).localname != "TextRegion" or nested[0].get("id") != f"c_{bid}"):
            raise ValueError(f"PAGE container mapping differs for {bid}")
        if block["category"] in ("titre", "texte", "legende", "autre"):
            expected_type = {"titre": "heading", "texte": "paragraph", "legende": "caption"}.get(block["category"], "other")
            if region.get("type") != expected_type:
                raise ValueError(f"PAGE text type differs for {bid}")
        for index, line_elem in enumerate(region.findall(".//p:TextLine", ns)):
            if int(line_elem.get("index")) != index:
                raise ValueError(f"PAGE line index differs for {bid}")
            lid = mapping(line_elem.get("id"), "l")
            block["line_ids"].append(lid)
            line = {"id": lid, "block_id": bid, "polygon": _parse_points(line_elem.find("p:Coords", ns).get("points")), "baseline": _parse_points(line_elem.find("p:Baseline", ns).get("points")), "text": line_elem.findtext("p:TextEquiv/p:Unicode", default="", namespaces=ns), "word_ids": [], **json.loads(line_elem.get("custom"))}
            for word_elem in line_elem.findall("p:Word", ns):
                wid = mapping(word_elem.get("id"), "w")
                line["word_ids"].append(wid)
                words.append({"id": wid, "line_id": lid, "polygon": _parse_points(word_elem.find("p:Coords", ns).get("points")), "text": word_elem.findtext("p:TextEquiv/p:Unicode", default="", namespaces=ns), **json.loads(word_elem.get("custom"))})
            lines.append(line)
        content = region if ET.QName(region).localname == "TextRegion" else region.find("p:TextRegion", ns)
        if block["line_ids"]:
            actual = content.findtext("p:TextEquiv/p:Unicode", default="", namespaces=ns)
            expected = "\n".join(line["text"] for line in lines if line["block_id"] == bid)
            if actual != expected:
                raise ValueError(f"PAGE region transcription differs for {bid}")
        blocks.append(block)
    return {"page_id": root.get("pcGtsId", "").removeprefix("p_"), "language": {"French": "fr"}.get(elem.get("primaryLanguage")), "image": {"width": int(elem.get("imageWidth")), "height": int(elem.get("imageHeight")), "path": elem.get("imageFilename")}, "articles": articles, "blocks": blocks, "lines": lines, "words": words, "reading_order": {"block_ids": ordered, "unordered_block_ids": unordered, "line_ids": [line["id"] for line in lines]}}


def _alto_read(root):
    ns = {"a": ALTO_NS}
    if root.get("SCHEMAVERSION") != "4.4":
        raise ValueError("ALTO SCHEMAVERSION must be 4.4")
    tags = {tag.get("ID"): tag for tag in root.find("a:Tags", ns)}

    def metadata(elem, kind):
        return [tags[ref] for ref in elem.get("TAGREFS", "").split() if tags[ref].get("TYPE") == "mille-feuilles:" + kind]

    def label(elem, kind):
        found = metadata(elem, kind)
        if len(found) != 1:
            raise ValueError(f"ALTO expected one {kind} tag for {elem.get('ID')}")
        return found[0].get("LABEL")

    def polygon(elem):
        points = _parse_points(elem.find("a:Shape/a:Polygon", ns).get("POINTS"))
        actual = [float(elem.get(key)) for key in ("HPOS", "VPOS", "WIDTH", "HEIGHT")]
        if any(not math.isfinite(a) or abs(a - b) > 1e-6 for a, b in zip(actual, _bbox(points))):
            raise ValueError(f"ALTO bbox differs for {elem.get('ID')}")
        return points

    articles = [{"id": tag.get("LABEL"), **json.loads(tag.get("DESCRIPTION"))} for tag in tags.values() if tag.get("TYPE") == "mille-feuilles:article"]
    ordered = [n.get("REF").removeprefix("b_") for n in root.findall("a:ReadingOrder/a:OrderedGroup/a:ElementRef", ns)]
    unordered = [n.get("REF").removeprefix("b_") for n in root.findall("a:ReadingOrder/a:UnorderedGroup/a:ElementRef", ns)]
    elem = root.find("a:Layout/a:Page", ns)
    blocks, lines, words = [], [], []
    for block_elem in elem.find("a:PrintSpace", ns):
        bid = block_elem.get("ID").removeprefix("b_")
        article_tags = metadata(block_elem, "article")
        if len(article_tags) > 1:
            raise ValueError(f"ALTO multiple articles for {bid}")
        block = {"id": bid, "category": label(block_elem, "category"), "article_id": article_tags[0].get("LABEL") if article_tags else None, "polygon": polygon(block_elem), "line_ids": []}
        if ET.QName(block_elem).localname != _alto_kind(block):
            raise ValueError(f"ALTO block type differs for {bid}")
        for line_elem in block_elem.findall("a:TextLine", ns):
            lid = line_elem.get("ID").removeprefix("l_")
            block["line_ids"].append(lid)
            line = {"id": lid, "block_id": bid, "polygon": polygon(line_elem), "baseline": _parse_points(line_elem.get("BASELINE")), "legibility": label(line_elem, "legibility"), "word_ids": [], "text": ""}
            string_nodes = line_elem.findall("a:String", ns)
            gap_tags = metadata(line_elem, "spaces")
            if len(gap_tags) > 1:
                raise ValueError(f"ALTO multiple spaces tags for {lid}")
            gaps = json.loads(gap_tags[0].get("DESCRIPTION")) if gap_tags else [1] * (len(string_nodes) - 1)
            if len(gaps) != len(string_nodes) - 1 or any(type(g) is not int or g < 0 for g in gaps):
                raise ValueError(f"ALTO invalid spaces metadata for {lid}")
            for index, word_elem in enumerate(string_nodes):
                wid = word_elem.get("ID").removeprefix("w_")
                line["word_ids"].append(wid)
                text = word_elem.get("CONTENT")
                start = len(line["text"])
                line["text"] += text
                hyps = metadata(word_elem, "hyphenation")
                hyp = None
                if hyps:
                    if len(hyps) != 1 or word_elem.get("SUBS_TYPE") not in ("HypPart1", "HypPart2"):
                        raise ValueError(f"ALTO invalid hyphenation for {wid}")
                    hyp = {"group_id": hyps[0].get("LABEL"), "part": "start" if word_elem.get("SUBS_TYPE") == "HypPart1" else "end", "reconstructed_text": word_elem.get("SUBS_CONTENT")}
                    if hyp["reconstructed_text"] != hyps[0].get("DESCRIPTION"):
                        raise ValueError(f"ALTO hyphenation tag mismatch for {wid}")
                elif word_elem.get("SUBS_TYPE") or word_elem.get("SUBS_CONTENT"):
                    raise ValueError(f"ALTO unexpected substitution for {wid}")
                words.append({"id": wid, "line_id": lid, "polygon": polygon(word_elem), "text": text, "char_span": [start, len(line["text"])], "legibility": label(word_elem, "legibility"), "hyphenation": hyp})
                next_elem = word_elem.getnext()
                has_space = next_elem is not None and ET.QName(next_elem).localname == "SP"
                expected_space = index < len(gaps) and gaps[index] > 0
                if has_space != expected_space:
                    raise ValueError(f"ALTO space element differs after {wid}")
                if index < len(gaps):
                    line["text"] += " " * gaps[index]
            if line_elem.find("a:HYP", ns) is not None:
                raise ValueError(f"Unexpected ALTO HYP element in {lid}")
            lines.append(line)
        blocks.append(block)
    return {"page_id": elem.get("ID", "").removeprefix("p_"), "language": elem.get("LANG"), "image": {"width": float(elem.get("WIDTH")), "height": float(elem.get("HEIGHT")), "path": root.findtext("a:Description/a:sourceImageInformation/a:fileName", namespaces=ns)}, "articles": articles, "blocks": blocks, "lines": lines, "words": words, "reading_order": {"block_ids": ordered, "unordered_block_ids": unordered, "line_ids": [line["id"] for line in lines]}}


def _compare_roundtrip(expected, actual, kind):
    errors = []
    for key in ("width", "height", "path"):
        if expected["image"][key] != actual["image"][key]:
            errors.append(f"{kind} image.{key} differs")
    for key in ("page_id", "language", "articles", "reading_order"):
        if expected[key] != actual[key]:
            errors.append(f"{kind} {key} differs")
    for collection in ("blocks", "lines", "words"):
        items = {item["id"]: item for item in actual[collection]}
        if len(items) != len(actual[collection]) or set(items) != {i["id"] for i in expected[collection]}:
            errors.append(f"{kind} {collection} identifiers differ")
        for item in expected[collection]:
            other = items.get(item["id"])
            if other is None:
                continue
            for key, value in item.items():
                if key == "extensions":
                    continue
                if key in ("polygon", "baseline"):
                    points = other.get(key, [])
                    projection = _rounded(value, expected, polygon=key == "polygon") if kind == "page" else value
                    if len(projection) != len(points) or any(abs(a - b) > 1e-6 for p, q in zip(projection, points) for a, b in zip(p, q)):
                        errors.append(f"{kind} {item['id']}.{key} differs")
                elif value != other.get(key):
                    errors.append(f"{kind} {item['id']}.{key} differs")
    return errors


def _validate_coco(root, pages):
    data = json.loads(_lot_path(root, "exports/coco/instances.json").read_text(encoding="utf-8"))
    errors = []
    expected_categories = [{"id": i, "name": name} for i, name in enumerate(CATEGORIES, 1)]
    if data["categories"] != expected_categories:
        errors.append("coco categories differ")
    mapping = data["mille_feuilles_id_mapping"]
    if len(data["images"]) != len(pages) or len(data["annotations"]) != sum(len(p["blocks"]) for p in pages):
        errors.append("coco object counts differ")
    image_ids, annotation_ids = set(), set()
    actual_pages, actual_blocks = set(), set()
    page_map = {page["page_id"]: page for page in pages}
    block_map = {(page["page_id"], block["id"]): block for page in pages for block in page["blocks"]}
    for image in data["images"]:
        iid = image["id"]
        if type(iid) is not int or iid <= 0 or iid in image_ids:
            errors.append("coco image IDs invalid or duplicated")
        image_ids.add(iid)
        pid = mapping["images"][str(iid)]
        actual_pages.add(pid)
        page = page_map[pid]
        if any(image[key] != page["image"][field] for key, field in (("width", "width"), ("height", "height"), ("file_name", "path"))):
            errors.append(f"coco image {pid} differs")
    for annotation in data["annotations"]:
        aid = annotation["id"]
        if type(aid) is not int or aid <= 0 or aid in annotation_ids:
            errors.append("coco annotation IDs invalid or duplicated")
        annotation_ids.add(aid)
        ref = mapping["annotations"][str(aid)]
        key = (ref["page_id"], ref["block_id"])
        actual_blocks.add(key)
        block = block_map[key]
        expected = {"category_id": CATEGORIES.index(block["category"]) + 1, "segmentation": [[v for p in block["polygon"] for v in p]], "bbox": _bbox(block["polygon"]), "area": _area(block["polygon"]), "iscrowd": 0}
        if annotation["image_id"] not in image_ids or mapping["images"].get(str(annotation["image_id"])) != ref["page_id"]:
            errors.append(f"coco {key} image reference differs")
        for field, value in expected.items():
            if annotation.get(field) != value:
                errors.append(f"coco {key}.{field} differs")
    if actual_pages != set(page_map) or actual_blocks != set(block_map):
        errors.append("coco canonical mapping differs")
    if set(mapping["images"]) != {str(i) for i in image_ids} or set(mapping["annotations"]) != {str(i) for i in annotation_ids}:
        errors.append("coco extra or missing mapping entries")
    return errors


def validate_exports(root: Path, pages: list[dict]) -> list[str]:
    """Validate pinned XSDs, XML roundtrips and COCO. Return diagnostic errors."""
    root = Path(root)
    errors = []
    try:
        provenance = json.loads((SCHEMA_DIR / "provenance.json").read_text(encoding="utf-8"))
        for item in provenance["files"]:
            if hashlib.sha256((SCHEMA_DIR / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
                errors.append(f"XML schema hash differs: {item['path']}")
    except (OSError, ValueError, KeyError) as exc:
        errors.append(f"XML schema provenance: {exc}")
    for page in pages:
        try:
            pid = _page_id(page)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f"exports: {exc}")
            continue
        try:
            report = json.loads(_lot_path(root, f"exports/reports/{pid}.json").read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise ValueError("export report must be a JSON object")
            paths = {kind: f"exports/{kind}/{pid}.xml" for kind in ("page", "alto")}
            paths["report"] = f"exports/reports/{pid}.json"
            for field, expected in _export_report(page, paths).items():
                if field not in report or report[field] != expected:
                    errors.append(f"{pid}: export report {field} differs or is missing")
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f"{pid}: export report: {exc}")
        for kind, reader in (("page", _page_read), ("alto", _alto_read)):
            try:
                doc = ET.parse(str(_lot_path(root, f"exports/{kind}/{pid}.xml")), _parser())
                if doc.docinfo.doctype:
                    raise ValueError("DOCTYPE is not allowed")
                _schema(kind).assertValid(doc)
                errors.extend(f"{pid}: {msg}" for msg in _compare_roundtrip(page, reader(doc.getroot()), kind))
            except (OSError, ET.Error, ValueError, KeyError, TypeError, AttributeError) as exc:
                errors.append(f"{pid}: {kind}: {exc}")
    try:
        errors.extend(_validate_coco(root, pages))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"coco: {exc}")
    return errors
