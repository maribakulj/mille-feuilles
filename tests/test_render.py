"""Independent checks of raster pixels, geometry and state isolation.

Only bundled synthetic assets are read. No historical corpus or frozen test is
used; every modified asset lives in a temporary directory.
"""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import shutil

from fontTools.ttLib import TTFont
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pytest
from shapely.geometry import LineString, Polygon

from mille_feuilles.render import Composer, Config, render_page
from mille_feuilles.validation import validate_page
from mille_feuilles.exports import export_page

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def assets_root(tmp_path):
    shutil.copytree(ROOT / "assets", tmp_path / "assets")
    assets = json.loads((tmp_path / "assets/catalog.json").read_text(encoding="utf-8"))["assets"]
    return tmp_path, assets


@pytest.fixture(scope="module")
def clean_page(tmp_path_factory):
    root = tmp_path_factory.mktemp("render_clean")
    shutil.copytree(ROOT / "assets", root / "assets")
    assets = json.loads((root / "assets/catalog.json").read_text(encoding="utf-8"))["assets"]
    config = Config(width=1200, height=1656, columns=5, degradation="clean", seed=127)
    page = render_page(config, 0, assets, root)
    return root, assets, config, page


def test_shaping_backend_is_explicit_and_matches_loaded_font(assets_root):
    root, assets = assets_root
    composer = Composer(Config(width=800, height=1100, columns=4), 0, assets, root)
    assert composer.regular.layout_engine == ImageFont.Layout.BASIC


def test_clean_png_is_grayscale_and_has_recorded_dimensions_and_hash(clean_page):
    root, _, config, page = clean_page
    path = root / page["image"]["path"]
    with Image.open(path) as image:
        assert image.mode == page["image"]["color_mode"] == "L"
        assert image.size == (config.width, config.height)
        assert image.info["dpi"] == pytest.approx((config.dpi, config.dpi), abs=0.02)
        pixels = np.asarray(image)
    assert page["image"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert pixels.min() < 100 and pixels.max() == 255
    assert np.all(pixels[:8] == 255) and np.all(pixels[-8:] == 255)
    assert np.all(pixels[:, :8] == 255) and np.all(pixels[:, -8:] == 255)


def test_annotated_envelopes_cover_every_clean_ink_pixel(clean_page):
    root, _, _, page = clean_page
    with Image.open(root / page["image"]["path"]) as image:
        actual = np.asarray(image).copy()
    mask = Image.new("1", (page["image"]["width"], page["image"]["height"]))
    draw = ImageDraw.Draw(mask)
    polygons = [word["polygon"] for word in page["words"]]
    polygons += [block["polygon"] for block in page["blocks"] if not block["line_ids"]]
    for polygon in polygons:
        # Pixel support touches a pixel if its footprint meets the envelope.
        left = math.floor(min(x for x, _ in polygon))
        top = math.floor(min(y for _, y in polygon))
        right = math.ceil(max(x for x, _ in polygon))
        bottom = math.ceil(max(y for _, y in polygon))
        draw.rectangle((left, top, right, bottom), fill=1)
    escaped = (actual < 250) & ~np.asarray(mask, dtype=bool)
    assert not escaped.any(), f"{escaped.sum()} ink pixels are outside all annotated objects"


def test_clean_glyph_pixels_are_recoverable_from_annotation_baselines(clean_page):
    root, assets, config, page = clean_page
    params = page["provenance"]["parameters"]
    font_paths = {asset["id"]: root / asset["path"] for asset in assets if asset["kind"] == "font"}
    fonts = {}
    lines = {line["id"]: line for line in page["lines"]}
    expected = Image.new("L", (config.width, config.height), 255)
    draw = ImageDraw.Draw(expected)
    assert params["shaping"]["engine"] == "pillow-freetype-basic"
    shaping = {}
    for word in page["words"]:
        line = lines[word["line_id"]]
        metadata = line["extensions"]["mf:font"]
        assert metadata["layout_engine"] == "BASIC"
        key = metadata["asset_id"], metadata["size"]
        if key not in fonts:
            fonts[key] = ImageFont.truetype(font_paths[key[0]], key[1], layout_engine=ImageFont.Layout.BASIC)
        font = fonts[key]
        left_bearing = font.getbbox(word["text"], anchor="ls", **shaping)[0]
        # The envelope includes overhang; derive the actual pen from its left
        # edge and use the recorded baseline, without renderer pen state.
        pen_x = min(x for x, _ in word["polygon"]) - min(0, left_bearing)
        baseline = line["baseline"][0][1]
        draw.text((pen_x, baseline), word["text"], anchor="ls", font=font,
                  fill=params["ink_level"], **shaping)
    for block in page["blocks"]:
        if block["category"] == "separateur":
            polygon = block["polygon"]
            draw.rectangle((polygon[0][0], polygon[0][1], polygon[2][0], polygon[2][1]),
                           fill=min(150, params["ink_level"] + 35))
    with Image.open(root / page["image"]["path"]) as image:
        difference = np.asarray(image) != np.asarray(expected)
    assert not difference.any(), f"{difference.sum()} pixels differ from annotation-derived rendering"


@pytest.mark.parametrize("columns,mode,index", [(4, "clean", 0), (5, "aged", 2), (6, "faint", 3)])
def test_small_pages_keep_words_lines_baselines_inside_image(assets_root, columns, mode, index):
    root, assets = assets_root
    config = Config(width=800, height=1100, columns=columns, degradation=mode)
    page = render_page(config, index, assets, root)
    assert page["words"], "A valid configuration must produce text"
    assert validate_page(page) == []
    lines = {line["id"]: line for line in page["lines"]}
    blocks = {block["id"]: block for block in page["blocks"]}
    for word in page["words"]:
        polygon = Polygon(word["polygon"])
        line = lines[word["line_id"]]
        assert Polygon(line["polygon"]).buffer(0.5).covers(polygon)
        for x, y in word["polygon"]:
            assert 0 <= x <= config.width and 0 <= y <= config.height
    for line in page["lines"]:
        poly = Polygon(line["polygon"])
        assert poly.buffer(0.5).covers(LineString(line["baseline"]))
        assert Polygon(blocks[line["block_id"]]["polygon"]).buffer(0.5).covers(poly)


@pytest.mark.parametrize("mode", ["clean", "aged", "faint"])
def test_page_reproduction_is_independent_of_other_pages_and_roots(assets_root, tmp_path, mode):
    root, assets = assets_root
    config = Config(width=800, height=1100, columns=4, degradation=mode, seed=400)
    first = render_page(config, 2, assets, root)
    first_bytes = (root / first["image"]["path"]).read_bytes()
    render_page(config, 1, assets, root)
    other = tmp_path / "isolated"
    shutil.copytree(root / "assets", other / "assets")
    second = render_page(config, 2, assets, other)
    assert first == second
    assert first_bytes == (other / second["image"]["path"]).read_bytes()


def test_unicode_source_document_provenance_survives_render(clean_page):
    root, assets, _, page = clean_page
    by_id = {asset["id"]: asset for asset in assets}
    for span in page["provenance"]["text_spans"]:
        source = by_id[span["asset_id"]]
        assert span["source_document_id"] == source["metadata"]["source_document_id"]
        raw = (root / source["path"]).read_text(encoding="utf-8")
        assert 0 <= span["start"] < span["end"] <= len(raw)
        assert raw[span["start"]:span["end"]].strip()
    for line in page["lines"]:
        words = {word["id"]: word for word in page["words"]}
        assert " ".join(words[wid]["text"] for wid in line["word_ids"]) == line["text"]
        for wid in line["word_ids"]:
            word = words[wid]
            start, end = word["char_span"]
            assert line["text"][start:end] == word["text"]


def test_rotated_rules_survive_page_integer_quantization(assets_root):
    # Actual 100-page pilot failure: a one-pixel rule at index 29 rounded its
    # first and last corners to the same PAGE point, despite a valid canonical.
    from lxml import etree

    root, assets = assets_root
    page = render_page(Config(seed=20261007), 29, assets, root)
    assert validate_page(page) == []
    paths = export_page(page, root)
    tree = etree.parse(str(root / paths["page"]))
    regions = tree.findall(".//{*}SeparatorRegion/{*}Coords")
    assert regions
    for region in regions:
        points = region.attrib["points"].split()
        assert len(points) >= 3 and len(set(points)) == len(points)


def test_reading_order_finishes_articles_and_preserves_cross_column_hyphens(clean_page):
    _, _, _, page = clean_page
    lines = {line["id"]: line for line in page["lines"]}
    blocks = {block["id"]: block for block in page["blocks"]}
    header_blocks = [blocks[bid] for bid in page["articles"][0]["block_ids"]]
    assert [b["category"] for b in header_blocks] == ["titre", "texte"]
    assert lines[header_blocks[0]["line_ids"][0]]["text"] == "MILLE FEUILLES"
    assert lines[header_blocks[1]["line_ids"][0]]["text"].startswith("Journal de démonstration")
    rank = {lid: index for index, lid in enumerate(page["reading_order"]["line_ids"])}
    block_rank = {bid: index for index, bid in enumerate(page["reading_order"]["block_ids"])}
    cross_column_articles = []
    for article in page["articles"]:
        positions = [block_rank[bid] for bid in article["block_ids"]]
        assert positions == list(range(positions[0], positions[0] + len(positions)))
        body_blocks = [blocks[bid] for bid in article["block_ids"] if blocks[bid]["category"] != "titre"]
        if len(body_blocks) > 1:
            cross_column_articles.append(article)
    assert cross_column_articles, "Fixture should exercise articles continued into another column"
    groups = {}
    for word in page["words"]:
        if word["hyphenation"]:
            groups.setdefault(word["hyphenation"]["group_id"], []).append(word)
    assert groups
    cross_column_groups = 0
    for parts in groups.values():
        assert len(parts) == 2
        first, second = sorted(parts, key=lambda word: rank[word["line_id"]])
        assert first["hyphenation"]["part"] == "start"
        assert second["hyphenation"]["part"] == "end"
        assert rank[second["line_id"]] == rank[first["line_id"]] + 1
        assert first["text"].endswith("-")
        assert first["text"][:-1] + second["text"] == first["hyphenation"]["reconstructed_text"]
        first_block = blocks[lines[first["line_id"]]["block_id"]]
        second_block = blocks[lines[second["line_id"]]["block_id"]]
        assert first_block["article_id"] == second_block["article_id"]
        cross_column_groups += first_block["id"] != second_block["id"]
    assert cross_column_groups, "Fixture should exercise a hyphen group across column blocks"


def test_missing_unicode_glyph_is_rejected_without_substitution(assets_root):
    root, assets = assets_root
    path = root / next(a["path"] for a in assets if a["id"] == "text_demo_fr")
    path.write_text(path.read_text(encoding="utf-8") + "\n\nCaractère absent : 🦉\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Glyphes absents"):
        render_page(Config(width=800, height=1100, columns=4), 0, assets, root)
    assert not (root / "images").exists()


def test_cmap_mapping_to_missing_glyph_is_rejected(assets_root):
    root, assets = assets_root
    path = root / next(a["path"] for a in assets if a["id"] == "font_oldstandard_regular")
    with TTFont(path) as font:
        for table in font["cmap"].tables:
            if table.isUnicode() and ord("é") in table.cmap:
                table.cmap[ord("é")] = ".notdef"
        font.save(path)
    with pytest.raises(ValueError, match="Glyphes absents"):
        render_page(Config(width=800, height=1100, columns=4), 0, assets, root)


def test_non_nfc_text_is_not_silently_normalized(assets_root):
    root, assets = assets_root
    path = root / next(a["path"] for a in assets if a["id"] == "text_demo_fr")
    path.write_text("Une e\u0301preuve composée.\n", encoding="utf-8")
    with pytest.raises(ValueError):
        render_page(Config(width=800, height=1100, columns=4), 0, assets, root)


def test_overwide_word_raises_instead_of_clipping(assets_root):
    root, assets = assets_root
    composer = Composer(Config(width=800, height=1100, columns=6), 0, assets, root)
    with pytest.raises(ValueError, match="Mot trop large"):
        composer.wrap("W" * 100 + "!", composer.regular, composer.col_w)


def test_long_multiline_title_is_never_silently_clipped(assets_root):
    root, assets = assets_root
    path = root / next(a["path"] for a in assets if a["id"] == "text_titres_fr")
    path.write_text(" ".join(["ÉDITION"] * 50) + "\n", encoding="utf-8")
    config = Config(width=800, height=1100, columns=4, degradation="clean", seed=120)
    try:
        page = render_page(config, 0, assets, root)
    except ValueError:
        # Explicit refusal is valid; a partially clipped PNG is not.
        assert not (root / "images").exists()
    else:
        for word in page["words"]:
            assert all(0 <= x <= config.width and 0 <= y <= config.height
                       for x, y in word["polygon"]), word


@pytest.mark.parametrize("overrides", [
    {"width": 799}, {"height": 1099}, {"columns": 3}, {"columns": 7},
    {"seed": -1}, {"seed": 2**53}, {"dpi": 0}, {"degradation": "unknown"},
])
def test_invalid_config_is_rejected(overrides):
    values = {"width": 800, "height": 1100, "columns": 4, "degradation": "clean"}
    values.update(deepcopy(overrides))
    with pytest.raises(ValueError):
        Config(**values).validate()
