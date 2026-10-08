"""Compose newspaper pages and annotations from the same font measurements.

Words are drawn individually at the recorded pen positions. The canonical text
is independent of glyph shaping; no OCR is used to recover annotations.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import unicodedata
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .catalog import text_assets_by_role, text_units
from .io import sha256, write_json

PROFILE = "fr_press_19c_columns_4_6"
PROFILE_MEASURED = "fr_press_19c_columns_4_6_measured"
PROFILE_LAYOUT = "fr_press_19c_layout_v2"
SCHEMA_VERSION = "0.3.0"
# An explicit portable Latin/NFC profile, not an environment-dependent fallback.
# BASIC renders the same precomposed glyphs used for measurement; discretionary
# OpenType ligatures and complex-script shaping are outside this profile.
SHAPING: dict = {}


@dataclass(frozen=True)
class Config:
    width: int = 2680
    height: int = 3698
    dpi: int = 150
    columns: int | None = None
    degradation: str = "mixed"
    seed: int = 20261007
    partition: str | None = None
    degradation_profile: dict | None = None
    layout_profile: str | None = None
    content_profile: str | None = None

    def validate(self) -> None:
        if not (800 <= self.width <= 6000 and 1100 <= self.height <= 8500):
            raise ValueError("Dimensions admises : 800–6000 × 1100–8500 pixels")
        if not 1.25 <= self.height / self.width <= 1.55:
            raise ValueError("Le profil exige un rapport hauteur/largeur entre 1,25 et 1,55")
        if not 40 <= self.dpi <= 400:
            raise ValueError("DPI attendu entre 40 et 400")
        if self.columns is not None and self.columns not in (4, 5, 6):
            raise ValueError("Le profil accepte 4, 5 ou 6 colonnes")
        if self.degradation not in ("clean", "aged", "faint", "mixed"):
            raise ValueError("Dégradation inconnue")
        if not 0 <= self.seed < 2**53:
            raise ValueError("Graine hors intervalle 0..2^53-1")
        if self.partition is not None and (
            not isinstance(self.partition, str)
            or re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", self.partition) is None
        ):
            raise ValueError("Nom de partition invalide")
        if self.degradation_profile is not None:
            from .degrade import check_profile

            check_profile(self.degradation_profile)
        if self.layout_profile not in (None, PROFILE_LAYOUT):
            raise ValueError("Profil de mise en page inconnu")
        if self.layout_profile is not None and self.degradation_profile is None:
            raise ValueError("Le profil de mise en page exige un degradation_profile explicite")
        if self.content_profile not in (None, "consecutive-v1"):
            raise ValueError("Profil de contenu inconnu")
        if self.content_profile is not None and self.layout_profile != PROFILE_LAYOUT:
            raise ValueError("Le profil de contenu exige le profil de mise en page v2")

    def as_dict(self) -> dict:
        value = asdict(self)
        if self.degradation_profile is None:
            del value["degradation_profile"]
        if self.layout_profile is None:
            del value["layout_profile"]
        if self.content_profile is None:
            del value["content_profile"]
        return value


def page_seed(seed: int, index: int) -> int:
    digest = hashlib.sha256(f"mille-feuilles-v0.2:{seed}:{index}".encode()).digest()
    return int.from_bytes(digest[:6], "big")


def box(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def envelope(polygons: list[list[list[float]]]) -> list[list[float]]:
    pts = [point for polygon in polygons for point in polygon]
    return box(
        min(p[0] for p in pts),
        min(p[1] for p in pts),
        max(p[0] for p in pts),
        max(p[1] for p in pts),
    )


def text_segments(path: Path) -> list[tuple[str, int, int]]:
    raw = path.read_text(encoding="utf-8")
    if unicodedata.normalize("NFC", raw) != raw:
        raise ValueError(f"Texte source non NFC : {path}")
    return text_units(raw, "body")


class Composer:
    def __init__(self, config: Config, index: int, assets: list[dict], asset_root: Path):
        config.validate()
        self.config = config
        self.index = index
        self.profile = deepcopy(config.degradation_profile)
        self.oversampling = self.profile["oversampling"] if self.profile is not None else 1
        self._raster_fonts = {}
        self.seed = page_seed(config.seed, index)
        self.rng = random.Random(self.seed)
        self.page_id = f"mf_{index:04d}"
        self.assets = assets
        self.asset_root = asset_root
        self.by_name = {Path(a["path"]).name: a for a in assets}
        for name in ("OldStandard-Regular.ttf", "OldStandard-Bold.ttf"):
            if name not in self.by_name:
                raise ValueError(f"Fonte requise absente du catalogue : {name}")
        self.text_roles = text_assets_by_role({"schema_version": SCHEMA_VERSION, "assets": assets})
        self.role_units = {}
        body_documents = []
        for role, documents in self.text_roles.items():
            units = []
            for source in documents:
                raw = (self.asset_root / source["path"]).read_text(encoding="utf-8")
                if unicodedata.normalize("NFC", raw) != raw:
                    raise ValueError(f"Texte source non NFC : {source['id']}")
                units.extend((source, text, start, end) for text, start, end in text_units(raw, role))
                if config.content_profile is not None and role == "body":
                    body_documents.append((source, raw))
            if not units:
                raise ValueError(f"Au moins une unité de texte requise pour le rôle {role}")
            self.role_units[role] = units
        if config.content_profile is not None:
            from .content import index_body_documents

            self.content_index = index_body_documents(body_documents)
        if config.layout_profile is not None:
            self._init_layout_v2()
        else:
            self.cols = config.columns or self.rng.choices([4, 5, 6], [1, 3, 6])[0]
            self.margin = round(config.width * 0.035)
            self.gutter = round(config.width * self.rng.uniform(0.007, 0.010))
            self.col_w = (config.width - 2 * self.margin - (self.cols - 1) * self.gutter) / self.cols
            self.font_size = max(10, round(self.col_w / self.rng.uniform(19.5, 21.5)))
        self.regular = self.font("OldStandard-Regular.ttf", self.font_size)
        self.bold = self.font("OldStandard-Bold.ttf", max(12, round(self.font_size * 1.25)))
        self.masthead = self.font("OldStandard-Bold.ttf", round(config.width * 0.040))
        ascent, descent = self.regular.getmetrics()
        self.spacing = max(self.font_size * 1.14, (ascent + descent) * 0.92)
        self.top = round(config.height * 0.102)
        self.bottom = config.height - self.margin
        self.x = self.margin
        self.y = self.top
        self.column = 0
        self.blocks: list[dict] = []
        self.lines: list[dict] = []
        self.words: list[dict] = []
        self.articles: list[dict] = []
        self.hyphen_number = 0
        self.used_spans: list[dict] = []
        self.template_article_ids: list[str] = []
        if self.profile is None:
            mode = config.degradation
            self.mode = self.rng.choice(["clean", "aged", "aged", "faint"]) if mode == "mixed" else mode
            self.paper = 255 if self.mode == "clean" else self.rng.randint(240, 251)
            self.ink = self.rng.randint(18, 38) if self.mode != "faint" else self.rng.randint(65, 85)
        else:
            # Profile choices must never consume the composition random stream.
            self.mode, self.paper, self.ink = "measured", 0, 255
        self.canvas = Image.new(
            "L", (config.width * self.oversampling, config.height * self.oversampling), self.paper
        )
        self.draw = ImageDraw.Draw(self.canvas)
        self._check_coverage()

    def font(self, name: str, size: int) -> ImageFont.FreeTypeFont:
        path = self.asset_root / self.by_name[name]["path"]
        return ImageFont.truetype(path, size=size, layout_engine=ImageFont.Layout.BASIC)

    def _init_layout_v2(self) -> None:
        from . import layout

        templates = [a for a in self.assets if a["id"] == "template_press_v2"]
        if len(templates) != 1 or templates[0]["kind"] != "template":
            raise layout.LayoutError("Un actif template_press_v2 unique est requis")
        template_path = self.asset_root / templates[0]["path"]
        if sha256(template_path) != templates[0]["sha256"]:
            raise layout.LayoutError("Empreinte du gabarit de mise en page incohérente")
        template = json.loads(template_path.read_text(encoding="utf-8"))
        if not isinstance(template, dict) or template.get("id") != "template_press_v2":
            raise layout.LayoutError("Gabarit de mise en page v2 invalide")
        self.layout_options = deepcopy(layout.check_options(template.get("layout_options")))
        if self.config.columns is not None:
            self.layout_options["main_columns"] = {
                "choice": [self.config.columns], "weights": [1],
            }
        self.margin = round(self.config.width * 0.035)
        # This order belongs to the v2 composition stream. Photometry and
        # oversampling never consume it or affect the chosen horizontal layout.
        self.gutter = round(self.config.width * self.rng.uniform(0.007, 0.010))
        self.layout_body_ratio = self.rng.uniform(19.5, 21.5)
        self._layout_fonts = {}
        self._layout_word_bounds = {}
        # Measure each distinct non-hyphenatable token, not every paragraph for
        # every column option. Oversized splittable units are rejected later as
        # individual composition candidates, without removing all column choices.
        width_units = self.role_units
        if self.config.content_profile is not None:
            # Ineligible documents are never sampled by this profile and must
            # not eliminate a column width for the eligible bodies.
            width_units = {**width_units, "body": [
                (document["asset"], text, start, end)
                for document in self.content_index["documents"]
                for text, start, end in document["units"]
            ]}
        self._layout_unbreakable = {
            role: sorted({word for _, text, _, _ in units for word in text.split()
                          if role == "title" or not word.isalpha() or len(word) < 8})
            for role, units in width_units.items()
        }
        self.font_size, self.hyphen_number = 10, 0
        self.layout_draws = layout.draw_layout(
            self.rng, self.layout_options,
            width=self.config.width, height=self.config.height,
            margin=self.margin, gutter=self.gutter, column_ok=self._v2_column_ok,
            rdc_column_ok=self._v2_column_ok,
        )
        self.layout_typography = {}
        main = self.layout_draws["zones"][0]
        main_width = main["columns"][0][1] - main["columns"][0][0]
        normal = max(10, round(main_width / self.layout_body_ratio))
        small = layout.small_body_size(normal, self.layout_options["small_body_ratio"])
        for zone in self.layout_draws["zones"]:
            self.layout_typography[zone["id"]] = {
                "normal_body_size": normal, "small_body_size": small,
                "line_spacing_normal": self._v2_spacing(normal),
                "line_spacing_small": self._v2_spacing(small),
            }
        self.cols = len(self.layout_draws["zones"][0]["columns"])
        self.col_w = (self.config.width - 2 * self.margin - (self.cols - 1) * self.gutter) / self.cols
        self.font_size = self.layout_typography["main"]["normal_body_size"]
        self.layout_rejected_candidates = {"headline": 0, "boxed_ad": 0, "ordinary": 0}
        self.layout_termination_rejections = {}

    def _v2_font(self, name: str, size: int) -> ImageFont.FreeTypeFont:
        key = name, size
        if key not in self._layout_fonts:
            self._layout_fonts[key] = self.font(name, size)
        return self._layout_fonts[key]

    def _v2_spacing(self, size: int) -> float:
        return max(size * 1.14, sum(self._v2_font("OldStandard-Regular.ttf", size).getmetrics()) * 0.92)

    def _v2_word_bounds(self, text: str, font: ImageFont.FreeTypeFont) -> tuple:
        """The same native annotation bounds as add_line, without drawing.

        Both raster factors are included for v2 fitting. This deliberately makes
        the composition independent of the chosen coverage sampling factor;
        final annotations still use only the support of the actual raster.
        """
        key = font.path, font.size, text
        if key not in self._layout_word_bounds:
            ascent, descent = font.getmetrics()
            advance = font.getlength(text, **SHAPING)
            native = font.getbbox(text, anchor="ls", **SHAPING)
            font_key = font.path, font.size
            if font_key not in self._raster_fonts:
                self._raster_fonts[font_key] = font.font_variant(size=font.size * 2)
            doubled = self._raster_fonts[font_key].getbbox(text, anchor="ls", **SHAPING)
            left = min(0, native[0], doubled[0] / 2)
            top = min(-ascent, native[1], doubled[1] / 2)
            right = max(advance, native[2], doubled[2] / 2)
            bottom = max(descent, native[3], doubled[3] / 2)
            self._layout_word_bounds[key] = advance, (left, top, right, bottom)
        return self._layout_word_bounds[key]

    def _v2_row_bounds(self, tokens: list[dict], font: ImageFont.FreeTypeFont,
                       width: float, justify: bool) -> list[float]:
        measured = [self._v2_word_bounds(t["text"], font) for t in tokens]
        space = font.getlength(" ", **SHAPING)
        if justify and len(tokens) > 3:
            space = min(space * 2.7, max(space, (width - sum(a for a, _ in measured)) / (len(tokens) - 1)))
        bounds, pen = [], 0.0
        for advance, (left, top, right, bottom) in measured:
            bounds.append([pen + left, top, pen + right, bottom])
            pen += advance + space
        return [min(b[0] for b in bounds), min(b[1] for b in bounds),
                max(b[2] for b in bounds), max(b[3] for b in bounds)]

    def _v2_rows(self, text: str, font: ImageFont.FreeTypeFont, width: float,
                 *, hyphenate: bool, justify: bool) -> tuple[list[dict], int]:
        """Plan complete rows; rejected trials never consume hyphen IDs."""
        from .layout import LayoutError

        original_size, original_hyphen = self.font_size, self.hyphen_number
        available = width
        try:
            self.font_size = font.size
            for _ in range(8):
                self.hyphen_number = original_hyphen
                if available <= 0:
                    break
                rows = self.wrap(text, font, available, hyphenate)
                planned = []
                excess = 0.0
                for index, tokens in enumerate(rows):
                    justified = justify and index < len(rows) - 1
                    bounds = self._v2_row_bounds(tokens, font, available, justified)
                    excess = max(excess, bounds[2] - bounds[0] - width)
                    planned.append({"tokens": tokens, "font": font, "width": available,
                                    "justify": justified, "bounds": bounds})
                if excess <= 1e-7:
                    return planned, self.hyphen_number
                available -= excess + 1
            raise LayoutError("Enveloppe glyphique trop large pour la colonne")
        finally:
            self.font_size, self.hyphen_number = original_size, original_hyphen

    def _v2_column_ok(self, width: float, main_width: float | None = None) -> bool:
        """Reject unusable column choices before the planner draws a count."""
        from .layout import small_body_size

        normal = max(10, round((width if main_width is None else main_width) / self.layout_body_ratio))
        sizes = {normal, small_body_size(normal, self.layout_options["small_body_ratio"])}
        inset = max(self.layout_options["box_padding_px"]) + 2
        title_width = width - 2 * inset if self.layout_options["boxed_ad_probability"] else width
        for size in sorted(sizes):
            regular = self._v2_font("OldStandard-Regular.ttf", size)
            bold = self._v2_font("OldStandard-Bold.ttf", max(12, round(size * 1.25)))
            for role in ("title", "body", "advertisement"):
                available = width if role == "body" else title_width
                font = bold if role == "title" else regular
                for token in self._layout_unbreakable[role]:
                    _, bounds = self._v2_word_bounds(token, font)
                    if bounds[2] - bounds[0] > available:
                        return False
        return True

    @staticmethod
    def _v2_placed(row: dict, x: float, baseline: float, column: int, kind: str) -> dict:
        return {**row, "x": x - row["bounds"][0], "baseline": baseline,
                "column": column, "kind": kind}

    @staticmethod
    def _v2_bounds(rows: list[dict]) -> list[float]:
        return [min(r["x"] + r["bounds"][0] for r in rows),
                min(r["baseline"] + r["bounds"][1] for r in rows),
                max(r["x"] + r["bounds"][2] for r in rows),
                max(r["baseline"] + r["bounds"][3] for r in rows)]

    @staticmethod
    def _v2_native_width(rows: list[dict]) -> float:
        """Actual native headline envelope; never substitute its reservation.

        The ×2 annotations also contain this native support, so checking this
        narrower envelope makes the decision independent of raster factor.
        """
        lefts, rights = [], []
        for row in rows:
            font, pen = row["font"], row["x"]
            space = font.getlength(" ", **SHAPING)
            for token in row["tokens"]:
                text = token["text"]
                advance = font.getlength(text, **SHAPING)
                bounds = font.getbbox(text, anchor="ls", **SHAPING)
                lefts.append(pen + min(0, bounds[0]))
                rights.append(pen + max(advance, bounds[2]))
                pen += advance + space
        return max(rights) - min(lefts)

    def _v2_balance(self, rows: list[dict], rects: list[list[float]], spacing: float) -> dict | None:
        """Distribute a complete segment across all headline columns."""
        per_column, extra = divmod(len(rows), len(rects))
        if per_column < 2:
            return None
        placed, offset = [], 0
        for column, rect in enumerate(rects):
            count = per_column + (column < extra)
            chunk = rows[offset:offset + count]
            baseline = rect[1] - chunk[0]["bounds"][1]
            for row in chunk:
                if baseline + row["bounds"][3] > rect[3]:
                    return None
                placed.append(self._v2_placed(row, rect[0], baseline, column, "body"))
                baseline += spacing
            offset += count
        return {"rows": placed, "bottom": self._v2_bounds(placed)[3]}

    def _v2_fit(self, body: list[dict], heading: list[dict], rects: list[list[float]],
                cursor: tuple[int, float], spacing: float, padding: int | None = None) -> dict | None:
        """Fit a whole article before touching pixels, IDs or source spans."""
        for first_column in range(cursor[0], len(rects)):
            first_y = cursor[1] if first_column == cursor[0] else rects[first_column][1]
            inset = padding + 2 if padding is not None else 0
            column = first_column
            x0, top, _x1, bottom = rects[column]
            y = max(top, first_y) + inset
            bottom -= inset
            placed = []
            for row in heading:
                baseline = y - row["bounds"][1]
                placed.append(self._v2_placed(row, x0 + inset, baseline, column, "heading"))
                y = baseline + row["bounds"][3] + 2
            if y - body[0]["bounds"][1] + body[0]["bounds"][3] > bottom:
                continue
            baseline = y - body[0]["bounds"][1]
            for index, row in enumerate(body):
                if baseline + row["bounds"][3] > bottom:
                    if padding is not None or column + 1 >= len(rects):
                        break
                    column += 1
                    x0, top, _x1, bottom = rects[column]
                    baseline = top - row["bounds"][1]
                if baseline + row["bounds"][3] > bottom:
                    break
                placed.append(self._v2_placed(row, x0 + inset, baseline, column, "body"))
                if index == len(body) - 1:
                    end = baseline + row["bounds"][3] + inset + spacing * 0.6
                    return {"rows": placed, "cursor": (column, end)}
                baseline += spacing
            if padding is None:
                # Starting later cannot add capacity to a flowing article.
                return None
        return None

    def _v2_span(self, unit: tuple, article: dict, block_ids: list[str]) -> None:
        source, _, start, end = unit
        self.used_spans.append({
            "asset_id": source["id"], "start": start, "end": end,
            "source_document_id": source["metadata"]["source_document_id"],
            "article_id": article["id"], "block_ids": block_ids,
        })

    def _v2_body(self, role: str) -> tuple[tuple, dict | None]:
        if self.config.content_profile is None or role != "body":
            # Keep exactly the historical draw when the option is absent.
            return self.rng.choice(self.role_units[role]), None
        from .content import choose_body_sequence

        sequence = choose_body_sequence(self.content_index, self.rng)
        unit = (sequence["source"], sequence["text"], sequence["start"], sequence["end"])
        receipt = {"version": "1", "asset_id": sequence["source"]["id"],
                   "start": sequence["start"], "end": sequence["end"],
                   "unit_range": list(sequence["unit_range"])}
        return unit, receipt

    def _v2_commit(self, candidate: dict) -> dict:
        article = self.article()
        meta = candidate["metadata"]
        article["extensions"] = {"mf:layout": meta}
        if candidate.get("source_sequence") is not None:
            article["extensions"]["mf:source_sequence"] = deepcopy(candidate["source_sequence"])
        block, previous = None, None
        blocks_by_kind = {"heading": [], "body": []}
        for row in candidate["rows"]:
            key = row["kind"], row["column"]
            if key != previous:
                category = "annonce" if candidate["ad"] else ("titre" if key[0] == "heading" else "texte")
                block = self.block(category, article)
                blocks_by_kind[key[0]].append(block["id"])
                previous = key
            self.add_line(row["tokens"], block, row["x"], row["baseline"], row["font"],
                          row["width"], justify=row["justify"])
        if blocks_by_kind["heading"]:
            self._v2_span(candidate["title"], article, blocks_by_kind["heading"])
        self._v2_span(candidate["body"], article, blocks_by_kind["body"])
        self.hyphen_number = candidate["next_hyphen"]
        if meta["headline"] is not None:
            meta["headline"]["block_id"] = blocks_by_kind["heading"][0]
        if candidate["padding"] is not None:
            # The frame follows actual annotations, not a nominal justified
            # width; all four interior gaps are exactly the recorded padding.
            polygons = [b["polygon"] for b in self.blocks if b["article_id"] == article["id"]]
            content = envelope(polygons)
            inset = candidate["padding"] + 2
            x0, y0 = content[0][0] - inset, content[0][1] - inset
            x1, y1 = content[2][0] + inset, content[2][1] + inset
            rule_ids = []
            for rect in ([x0, y0, x1, y0 + 2], [x1 - 2, y0, x1, y1],
                         [x0, y1 - 2, x1, y1], [x0, y0, x0 + 2, y1]):
                self.separator(*rect)
                rule_ids.append(self.blocks[-1]["id"])
            meta["box"] = {"padding": candidate["padding"], "rule_ids": rule_ids,
                           "bbox": [x0, y0, x1, y1]}
        return article

    def _v2_type(self, zone_id: str, role: str) -> tuple[dict, ImageFont.FreeTypeFont, float]:
        typo = self.layout_typography[zone_id]
        requested = self.rng.random() < self.layout_options["small_body_probability"][role]
        size = typo["small_body_size"] if requested else typo["normal_body_size"]
        metadata = {"zone_id": zone_id, "body_font_size": size,
                    "small_body_requested": requested, "small_body": size < typo["normal_body_size"],
                    "headline": None, "box": None}
        spacing = typo["line_spacing_small"] if requested else typo["line_spacing_normal"]
        return metadata, self._v2_font("OldStandard-Regular.ttf", size), spacing

    def _v2_headline(self, zone: dict) -> tuple[int, float]:
        from . import layout

        meta, font, spacing = self._v2_type(zone["id"], "body")
        headline_font = self._v2_font("OldStandard-Bold.ttf", max(12, round(font.size * 2)))
        area = layout.headline_rect(self.layout_plan, zone["id"])
        for attempt in range(1, 33):
            body, source_sequence = self._v2_body("body")
            title = self.rng.choice(self.role_units["title"])
            try:
                headings, _ = self._v2_rows(title[1], headline_font, area[2] - area[0],
                                           hyphenate=False, justify=False)
                placed, y = [], area[1]
                for row in headings:
                    baseline = y - row["bounds"][1]
                    placed.append(self._v2_placed(row, area[0], baseline, 0, "heading"))
                    y = baseline + row["bounds"][3] + 2
                single_width = zone["columns"][0][1] - zone["columns"][0][0]
                if self._v2_native_width(placed) <= single_width + self.gutter:
                    raise layout.LayoutError("Le titre large ne dépasse pas une colonne et sa gouttière")
                # Preview uses a common ×1/×2 envelope; both reservations do too.
                headline_bottom = self._v2_bounds(placed)[3]
                plan = layout.reserve_headline(self.layout_plan, zone["id"], headline_bottom, spacing * 0.35)
                rects = layout.headline_columns(plan, zone["id"])
                body_rows, next_hyphen = self._v2_rows(
                    body[1], font, rects[0][2] - rects[0][0], hyphenate=True, justify=True,
                )
                fit = self._v2_balance(body_rows, rects, spacing)
                if fit is not None:
                    normal = self.layout_typography[zone["id"]]["normal_body_size"]
                    normal_height = sum(self._v2_font("OldStandard-Regular.ttf", normal).getmetrics())
                    plan = layout.reserve_headline_band(
                        plan, zone["id"], fit["bottom"], spacing * 0.6,
                        max(normal_height, self.layout_typography[zone["id"]]["line_spacing_normal"]),
                    )
            except ValueError:
                fit = None
            if fit is None:
                self.layout_rejected_candidates["headline"] += 1
                continue
            self.layout_plan = plan
            accepted_zone = next(z for z in plan["zones"] if z["id"] == zone["id"])
            reserved = accepted_zone["headline_reserved"]
            meta["headline"] = {"block_id": None, "reservation_bbox": deepcopy(reserved),
                                "body_column_indices": sorted({row["column"] for row in fit["rows"]}),
                                "attempts": attempt}
            self._v2_commit({"metadata": meta, "rows": placed + fit["rows"], "body": body,
                             "title": title, "ad": False, "padding": None,
                             "source_sequence": source_sequence,
                             "next_hyphen": next_hyphen})
            return (0, accepted_zone["headline_body_band"][3])
        raise layout.LayoutError("Aucun article complet ne tient sous le titre large après 32 essais")

    def _v2_zone(self, zone: dict) -> None:
        from . import layout

        before = len(self.articles)
        if zone["headline_span"] is not None:
            cursor = self._v2_headline(zone)
        else:
            cursor = (0, zone["bbox"][1])
        rects = layout.columns_below(self.layout_plan, zone["id"])
        rejected = 0
        pending_rejections = {"boxed_ad": 0, "ordinary": 0}
        while rejected < 32:
            ad = self.rng.random() < 0.18
            role = "advertisement" if ad else "body"
            meta, font, spacing = self._v2_type(zone["id"], role)
            boxed = ad and self.rng.random() < self.layout_options["boxed_ad_probability"]
            padding = self.rng.randint(*self.layout_options["box_padding_px"]) if boxed else None
            body, source_sequence = self._v2_body(role)
            title = self.rng.choice(self.role_units["title"])
            wants_title = self.rng.random() < (0.25 if ad else 0.55)
            width = rects[0][2] - rects[0][0] - (2 * (padding + 2) if boxed else 0)
            try:
                rows, next_hyphen = self._v2_rows(body[1], font, width, hyphenate=True, justify=True)
                heading = []
                if wants_title:
                    bold = self._v2_font("OldStandard-Bold.ttf", max(12, round(font.size * 1.25)))
                    heading, _ = self._v2_rows(title[1], bold, width, hyphenate=False, justify=False)
                fit = self._v2_fit(rows, heading, rects, cursor, spacing, padding)
            except ValueError:
                fit = None
            if fit is None:
                rejected += 1
                pending_rejections["boxed_ad" if boxed else "ordinary"] += 1
                continue
            for kind, count in pending_rejections.items():
                self.layout_rejected_candidates[kind] += count
            self._v2_commit({"metadata": meta, "rows": fit["rows"], "body": body,
                             "title": title, "ad": ad, "padding": padding,
                             "source_sequence": source_sequence,
                             "next_hyphen": next_hyphen})
            cursor = fit["cursor"]
            rejected = 0
            pending_rejections = {"boxed_ad": 0, "ordinary": 0}
        self.layout_termination_rejections[zone["id"]] = rejected
        if len(self.articles) == before:
            raise layout.LayoutError(f"Aucun article complet ne tient dans la zone {zone['id']}")

    def _content_v2(self) -> None:
        from . import layout

        header = self.article()
        self.template_article_ids.append(header["id"])
        title = self.block("titre", header)
        heading = "MILLE FEUILLES"
        head_width = self.masthead.getlength(heading, **SHAPING)
        baseline = self.margin + self.masthead.getmetrics()[0]
        self.add_line([{"text": word} for word in heading.split()], title,
                      (self.config.width - head_width) / 2, baseline, self.masthead, head_width)
        subtitle = "Journal de démonstration — Édition synthétique"
        metadata_block = self.block("texte", header)
        subfont = self.font("OldStandard-Regular.ttf", round(self.font_size * 1.25))
        subwidth = subfont.getlength(subtitle, **SHAPING)
        self.add_line([{"text": word} for word in subtitle.split()], metadata_block,
                      (self.config.width - subwidth) / 2, baseline + self.font_size * 2, subfont, subwidth)
        head_bounds = self._v2_row_bounds(
            [{"text": word} for word in heading.split()], self.masthead, head_width, False,
        )
        sub_bounds = self._v2_row_bounds(
            [{"text": word} for word in subtitle.split()], subfont, subwidth, False,
        )
        header_bottom = max(baseline + head_bounds[3], baseline + self.font_size * 2 + sub_bounds[3])
        self.top = max(self.top, baseline + self.font_size * 4, header_bottom + self.spacing * 2)
        self.separator(self.margin, self.top - self.spacing * 1.2,
                       self.config.width - self.margin, self.top - self.spacing * 1.2 + 2)
        self.layout_plan = layout.place_zones(
            self.layout_draws, top=self.top, bottom=self.bottom,
            min_zone_height=6 * max(t["line_spacing_normal"] for t in self.layout_typography.values()),
        )
        # Textual reading order is constructed article by article, main first.
        # Rules are never inserted in the ordered stream.
        for zone in self.layout_plan["zones"]:
            self._v2_zone(zone)
        if self.config.content_profile is not None and not any(
            "mf:source_sequence" in article.get("extensions", {}) for article in self.articles
        ):
            raise ValueError("Aucun corps multi-unités complet n'a été composé")
        for rect in self.layout_plan["zone_rules"]:
            self.separator(*rect)
        for zone in self.layout_plan["zones"]:
            reserved = zone["headline_reserved"]
            for index in range(1, len(zone["columns"])):
                x = (zone["columns"][index - 1][1] + zone["columns"][index][0]) / 2
                top = reserved[3] if reserved and index < zone["headline_span"] else zone["bbox"][1]
                self.separator(x - 1, top, x + 1, zone["bbox"][3])

    def _check_coverage(self) -> None:
        text = "MILLE FEUILLES Journal de démonstration — Édition synthétique -0123456789"
        for asset in self.assets:
            if asset["kind"] == "text":
                text += (self.asset_root / asset["path"]).read_text(encoding="utf-8")
        chars = set(text) - {"\n", "\r", "\t"}
        for name in ["OldStandard-Regular.ttf", "OldStandard-Bold.ttf"]:
            with TTFont(self.asset_root / self.by_name[name]["path"]) as font:
                cmap = font.getBestCmap() or {}
                missing = sorted(
                    c for c in chars if ord(c) not in cmap or font.getGlyphID(cmap[ord(c)]) == 0
                )
            if missing:
                raise ValueError(f"Glyphes absents dans {name}: {missing!r}")

    def article(self) -> dict:
        article = {"id": f"{self.page_id}_a{len(self.articles):04d}", "block_ids": []}
        self.articles.append(article)
        return article

    def block(self, category: str, article: dict | None) -> dict:
        block = {
            "id": f"{self.page_id}_b{len(self.blocks):04d}",
            "category": category,
            "polygon": [],
            "article_id": article["id"] if article else None,
            "line_ids": [],
        }
        self.blocks.append(block)
        if article:
            article["block_ids"].append(block["id"])
        return block

    def add_line(
        self,
        tokens: list[dict],
        block: dict,
        x: float,
        baseline: float,
        font: ImageFont.FreeTypeFont,
        width: float,
        justify: bool = False,
    ) -> None:
        line_id = f"{self.page_id}_l{len(self.lines):05d}"
        text = " ".join(token["text"] for token in tokens)
        total = sum(font.getlength(token["text"], **SHAPING) for token in tokens)
        space = font.getlength(" ", **SHAPING)
        if justify and len(tokens) > 3:
            space = min(space * 2.7, max(space, (width - total) / (len(tokens) - 1)))
        ascent, descent = font.getmetrics()
        pen = float(x)
        cursor = 0
        line_words = []
        for token in tokens:
            word_text = token["text"]
            advance = font.getlength(word_text, **SHAPING)
            left, top, right, bottom = font.getbbox(word_text, anchor="ls", **SHAPING)
            raster_font = font
            if self.oversampling > 1:
                key = font.path, font.size
                if key not in self._raster_fonts:
                    self._raster_fonts[key] = font.font_variant(size=font.size * self.oversampling)
                raster_font = self._raster_fonts[key]
                actual = raster_font.getbbox(word_text, anchor="ls", **SHAPING)
                # Layout and pen advances stay native. Hinting at twice the
                # size can change glyph support; include that support in the
                # annotation instead of changing line wraps or clipping glyphs.
                left, top = min(left, actual[0] / self.oversampling), min(top, actual[1] / self.oversampling)
                right, bottom = max(right, actual[2] / self.oversampling), max(bottom, actual[3] / self.oversampling)
            polygon = box(
                pen + min(0, left),
                baseline + min(-ascent, top),
                pen + max(advance, right),
                baseline + max(descent, bottom),
            )
            word = {
                "id": f"{self.page_id}_w{len(self.words):06d}",
                "line_id": line_id,
                "polygon": polygon,
                "text": word_text,
                "char_span": [cursor, cursor + len(word_text)],
                "legibility": "readable",
                "hyphenation": token.get("hyphenation"),
            }
            self.draw.text(
                (pen * self.oversampling, baseline * self.oversampling),
                word_text, fill=self.ink, font=raster_font, anchor="ls", **SHAPING
            )
            self.words.append(word)
            line_words.append(word)
            cursor += len(word_text) + 1
            pen += advance + space
        polygon = envelope([word["polygon"] for word in line_words])
        line = {
            "id": line_id,
            "block_id": block["id"],
            "polygon": polygon,
            "baseline": [[polygon[0][0], baseline], [polygon[1][0], baseline]],
            "text": text,
            "word_ids": [w["id"] for w in line_words],
            "legibility": "readable",
            "extensions": {
                "mf:font": {
                    "asset_id": self.by_name[Path(font.path).name]["id"],
                    "size": font.size,
                    "layout_engine": "BASIC",
                }
            },
        }
        self.lines.append(line)
        block["line_ids"].append(line_id)
        block["polygon"] = envelope([block["polygon"], polygon]) if block["polygon"] else polygon

    def wrap(
        self, text: str, font: ImageFont.FreeTypeFont, width: float, hyphenate: bool = True
    ) -> list[list[dict]]:
        pending = [{"text": word} for word in text.split()]
        result = []
        space = font.getlength(" ", **SHAPING)
        while pending:
            row: list[dict] = []
            occupied = 0.0
            while pending:
                token = pending[0]
                length = font.getlength(token["text"], **SHAPING)
                available = width - occupied - (space if row else 0)
                if length <= available:
                    row.append(pending.pop(0))
                    occupied += length + (space if len(row) > 1 else 0)
                    continue
                if (
                    hyphenate
                    and "hyphenation" not in token
                    and token["text"].isalpha()
                    and len(token["text"]) >= 8
                    and available > self.font_size * 2.5
                ):
                    splits = [
                        i
                        for i in range(3, len(token["text"]) - 2)
                        if font.getlength(token["text"][:i] + "-", **SHAPING) <= available
                    ]
                    if splits:
                        at = splits[-1]
                        group = f"{self.page_id}_h{self.hyphen_number:05d}"
                        self.hyphen_number += 1
                        original = token["text"]
                        row.append(
                            {
                                "text": original[:at] + "-",
                                "hyphenation": {
                                    "group_id": group,
                                    "part": "start",
                                    "reconstructed_text": original,
                                },
                            }
                        )
                        pending[0] = {
                            "text": original[at:],
                            "hyphenation": {
                                "group_id": group,
                                "part": "end",
                                "reconstructed_text": original,
                            },
                        }
                if not row:
                    raise ValueError(f"Mot trop large pour la colonne : {token['text']!r}")
                break
            result.append(row)
        return result

    def next_column(self) -> bool:
        self.column += 1
        self.x = self.margin + self.column * (self.col_w + self.gutter)
        self.y = self.top
        return self.column < self.cols

    def separator(self, x0: float, y0: float, x1: float, y1: float) -> None:
        # A one-pixel rule can lose a distinct corner after rotation and PAGE's
        # integer rounding. Keep both the raster and its composition envelope
        # at least two pixels thick; the exporter still rejects degenerate shapes.
        x1 = max(x1, x0 + 2)
        y1 = max(y1, y0 + 2)
        block = self.block("separateur", None)
        block["polygon"] = box(x0, y0, x1, y1)
        self.draw.rectangle(tuple(value * self.oversampling for value in (x0, y0, x1, y1)),
                            fill=200 if self.profile is not None else min(150, self.ink + 35))

    def content(self) -> None:
        header = self.article()
        self.template_article_ids.append(header["id"])
        title = self.block("titre", header)
        heading = "MILLE FEUILLES"
        head_width = self.masthead.getlength(heading, **SHAPING)
        baseline = self.margin + self.masthead.getmetrics()[0]
        self.add_line(
            [{"text": word} for word in heading.split()],
            title,
            (self.config.width - head_width) / 2,
            baseline,
            self.masthead,
            head_width,
        )
        subtitle = "Journal de démonstration — Édition synthétique"
        metadata_block = self.block("texte", header)
        subfont = self.font("OldStandard-Regular.ttf", round(self.font_size * 1.25))
        subwidth = subfont.getlength(subtitle, **SHAPING)
        self.add_line(
            [{"text": word} for word in subtitle.split()],
            metadata_block,
            (self.config.width - subwidth) / 2,
            baseline + self.font_size * 2,
            subfont,
            subwidth,
        )
        self.top = max(self.top, baseline + self.font_size * 4)
        self.y = self.top
        self.separator(
            self.margin,
            self.top - self.spacing * 1.2,
            self.config.width - self.margin,
            self.top - self.spacing * 1.2 + 2,
        )
        for col in range(1, self.cols):
            sep_x = self.margin + col * (self.col_w + self.gutter) - self.gutter / 2
            self.separator(
                sep_x, self.top - self.spacing / 3, sep_x + 1, self.bottom - self.spacing
            )
        bodies = self.role_units["body"]
        ads = self.role_units["advertisement"]
        titles = self.role_units["title"]
        while self.column < self.cols:
            if self.y + self.spacing * 6 > self.bottom:
                if not self.next_column():
                    break
            ad = self.rng.random() < 0.18
            segment = self.rng.choice(ads if ad else bodies)
            source, text, start, end = segment
            # Two successive paragraphs produce some cross-column articles.
            title_asset, title_text, title_start, title_end = self.rng.choice(titles)
            wants_title = self.rng.random() < (0.25 if ad else 0.55)
            wrapped = self.wrap(text, self.regular, self.col_w)
            heading_rows = (
                self.wrap(title_text, self.bold, self.col_w, False) if wants_title else []
            )
            title_height = len(heading_rows) * (sum(self.bold.getmetrics()) + 2)
            if title_height + self.spacing * 3 > self.bottom - self.top:
                raise ValueError("Titre trop haut pour une colonne du profil")
            if self.y + title_height + self.spacing * 3 > self.bottom:
                if not self.next_column():
                    break
            # Do not clip a word or split a hyphen group at the end of the page.
            remaining = int((self.bottom - self.y - title_height) / self.spacing)
            remaining += (self.cols - self.column - 1) * int(
                (self.bottom - self.top) / self.spacing
            )
            if len(wrapped) + 2 > remaining:
                break
            article = self.article()
            body_span = {
                "asset_id": source["id"],
                "start": start,
                "end": end,
                "source_document_id": source["metadata"]["source_document_id"],
                "article_id": article["id"],
                "block_ids": [],
            }
            self.used_spans.append(body_span)
            if wants_title:
                heading_block = self.block("annonce" if ad else "titre", article)
                for row in heading_rows:
                    self.y += self.bold.getmetrics()[0]
                    self.add_line(row, heading_block, self.x, self.y, self.bold, self.col_w)
                    self.y += self.bold.getmetrics()[1] + 2
                self.used_spans.append(
                    {
                        "asset_id": title_asset["id"],
                        "start": title_start,
                        "end": title_end,
                        "source_document_id": title_asset["metadata"]["source_document_id"],
                        "article_id": article["id"],
                        "block_ids": [heading_block["id"]],
                    }
                )
            block = self.block("annonce" if ad else "texte", article)
            body_span["block_ids"].append(block["id"])
            for i, row in enumerate(wrapped):
                if self.y + self.spacing > self.bottom:
                    if not self.next_column():
                        raise ValueError("Article dépassant la page après prévision de composition")
                    block = self.block("annonce" if ad else "texte", article)
                    body_span["block_ids"].append(block["id"])
                self.y += self.spacing
                self.add_line(
                    row,
                    block,
                    self.x,
                    self.y,
                    self.regular,
                    self.col_w,
                    justify=i < len(wrapped) - 1,
                )
            self.y += self.spacing * 0.55
            if self.y + self.spacing * 1.5 < self.bottom:
                length = self.col_w * self.rng.uniform(0.18, 0.45)
                center = self.x + self.col_w / 2
                self.separator(center - length / 2, self.y, center + length / 2, self.y + 1)
            self.y += self.spacing * 0.65

    def finish(self, out_root: Path) -> dict:
        if self.profile is not None:
            return self._finish_measured(out_root)
        self.content()
        transforms = []
        angle = 0.0 if self.mode == "clean" else self.rng.uniform(-0.35, 0.35)
        blur = 0.0 if self.mode == "clean" else self.rng.uniform(0.1, 0.3)
        if self.mode != "clean":
            np_rng = np.random.Generator(np.random.PCG64(self.seed))
            pixels = np.asarray(self.canvas, dtype=np.float32)
            noise = np_rng.normal(0, 0.55, pixels.shape).astype(np.float32)
            shade = np.linspace(-1.5, 1.5, pixels.shape[1], dtype=np.float32)[None, :]
            self.canvas = Image.fromarray(np.clip(pixels + noise + shade, 0, 255).astype(np.uint8))
            self.canvas = self.canvas.filter(ImageFilter.GaussianBlur(blur))
            transforms.append(
                {
                    "kind": "paper_noise_blur",
                    "geometry": "identity",
                    "parameters": {
                        "seed": self.seed,
                        "rng": "numpy.PCG64",
                        "noise_std": 0.55,
                        "shade_range": [-1.5, 1.5],
                        "blur_radius": blur,
                    },
                }
            )
        if angle:
            theta = math.radians(angle)
            c, s = math.cos(theta), math.sin(theta)
            cx, cy = self.config.width / 2, self.config.height / 2
            matrix = [[c, s, cx - c * cx - s * cy], [-s, c, cy + s * cx - c * cy], [0, 0, 1]]
            self.canvas = self.canvas.rotate(
                angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=self.paper
            )

            def transform(points: list[list[float]]) -> list[list[float]]:
                return [
                    [
                        round(matrix[0][0] * x + matrix[0][1] * y + matrix[0][2], 6),
                        round(matrix[1][0] * x + matrix[1][1] * y + matrix[1][2], 6),
                    ]
                    for x, y in points
                ]

            for obj in self.blocks + self.lines + self.words:
                obj["polygon"] = transform(obj["polygon"])
            for line in self.lines:
                line["baseline"] = transform(line["baseline"])
            transforms.append(
                {
                    "kind": "rotation",
                    "geometry": {"matrix": matrix},
                    "parameters": {
                        "degrees": angle,
                        "resampling": "bicubic",
                        "center": [cx, cy],
                        "fill": self.paper,
                    },
                }
            )
        image_path = out_root / "images" / f"{self.page_id}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        self.canvas.save(image_path, compress_level=6, dpi=(self.config.dpi, self.config.dpi))
        return self._page(image_path, transforms, angle, blur)

    def _page(self, image_path: Path, transforms: list[dict], angle: float, blur: float) -> dict:
        text_blocks = [b for b in self.blocks if b["line_ids"]]
        page = {
            "schema_version": SCHEMA_VERSION,
            "page_id": self.page_id,
            "profile": PROFILE,
            "image": {
                "path": f"images/{self.page_id}.png",
                "sha256": sha256(image_path),
                "width": self.config.width,
                "height": self.config.height,
                "color_mode": "L",
                "dpi": self.config.dpi,
            },
            "language": "fr",
            "provenance": {
                "seed": self.seed,
                "template_id": "template_press_v1",
                "asset_ids": [a["id"] for a in self.assets],
                "text_spans": self.used_spans,
                "extensions": {"mf:template_article_ids": self.template_article_ids},
                "parameters": {
                    "columns": self.cols,
                    "render_dpi": self.config.dpi,
                    "body_font_size": self.font_size,
                    "line_spacing": self.spacing,
                    "gutter": self.gutter,
                    "margin": self.margin,
                    "angle_degrees": angle,
                    "ink_level": self.ink,
                    "paper_level": self.paper,
                    "blur_radius": blur,
                    "degradation": self.mode,
                    "partition": self.config.partition,
                    "shaping": {
                        "engine": "pillow-freetype-basic",
                        "normalization": "NFC",
                        "direction": "ltr",
                        "discretionary_ligatures": False,
                    },
                },
            },
            "transforms": transforms,
            "articles": self.articles,
            "blocks": self.blocks,
            "lines": self.lines,
            "words": self.words,
            "reading_order": {
                "block_ids": [b["id"] for b in text_blocks],
                "unordered_block_ids": [b["id"] for b in self.blocks if not b["line_ids"]],
                "line_ids": [lid for b in text_blocks for lid in b["line_ids"]],
            },
        }
        if self.config.layout_profile is not None:
            page["profile"] = PROFILE_LAYOUT
            page["provenance"]["template_id"] = "template_press_v2"
            page["provenance"]["parameters"].update({
                "layout_profile": self.config.layout_profile,
                "layout": self.layout_plan,
                "layout_body_ratio": self.layout_body_ratio,
                "layout_typography": self.layout_typography,
                "layout_rejected_candidates": self.layout_rejected_candidates,
                "layout_termination_rejections": self.layout_termination_rejections,
            })
        if self.config.content_profile is not None:
            page["provenance"]["parameters"]["content_profile"] = self.config.content_profile
        return page

    def _finish_measured(self, out_root: Path) -> dict:
        from . import degrade, diagnostics

        if self.config.layout_profile is None:
            self.content()
        else:
            self._content_v2()
        angle = self.rng.uniform(-0.35, 0.35)
        theta = math.radians(angle)
        c, s = math.cos(theta), math.sin(theta)
        cx, cy = self.config.width / 2, self.config.height / 2
        matrix = [[c, s, cx - c * cx - s * cy], [-s, c, cy + s * cx - c * cy], [0, 0, 1]]

        def transform(points):
            return [[round(matrix[0][0] * x + matrix[0][1] * y + matrix[0][2], 6),
                     round(matrix[1][0] * x + matrix[1][1] * y + matrix[1][2], 6)]
                    for x, y in points]

        self.canvas = self.canvas.rotate(
            angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=0
        )
        for obj in self.blocks + self.lines + self.words:
            obj["polygon"] = transform(obj["polygon"])
        for line in self.lines:
            line["baseline"] = transform(line["baseline"])
        factor = self.oversampling
        native_size = [self.config.width, self.config.height]
        raster_size = [size * factor for size in native_size]
        transforms = []
        if factor > 1:
            transforms.append({
                "kind": "mf:oversampling",
                "geometry": {"matrix": [[factor, 0, 0], [0, factor, 0], [0, 0, 1]]},
                "parameters": {"factor": factor, "source_size": native_size, "target_size": raster_size},
            })
        raster_matrix = [
            [c, s, matrix[0][2] * factor], [-s, c, matrix[1][2] * factor], [0, 0, 1]
        ]
        transforms.append({
            "kind": "rotation", "geometry": {"matrix": raster_matrix},
            "parameters": {"degrees": angle, "resampling": "bicubic",
                           "center": [cx * factor, cy * factor], "fill": 0},
        })
        coverage = np.asarray(self.canvas, dtype=np.float32) / np.float32(255)
        if factor > 1:
            coverage = degrade.downsample_coverage(coverage, factor)
            transforms.append({
                "kind": "mf:downsample",
                "geometry": {"matrix": [[1 / factor, 0, 0], [0, 1 / factor, 0], [0, 0, 1]]},
                "parameters": {"factor": factor, "resampling": "box-mean",
                               "source_size": raster_size, "target_size": native_size},
            })
        mask = diagnostics.ideal_mask(coverage)
        resolved = degrade.sample_parameters(
            self.profile, degrade.degradation_seed(self.config.seed, self.index)
        )
        pixels, alterations = degrade.apply(coverage, resolved)
        transforms.extend(alterations)
        self.canvas = Image.fromarray(pixels)
        image_path = out_root / "images" / f"{self.page_id}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        self.canvas.save(image_path, compress_level=6, dpi=(self.config.dpi, self.config.dpi))
        page = self._page(image_path, transforms, angle, resolved.get("blur", {}).get("sigma_px", 0.0))
        page["profile"] = PROFILE_LAYOUT if self.config.layout_profile is not None else PROFILE_MEASURED
        paper, ink = degrade.reference_levels(resolved)
        page["provenance"]["parameters"].update({
            "degradation_profile": resolved,
            "oversampling": self.profile["oversampling"],
            "raster_width": raster_size[0], "raster_height": raster_size[1],
            "paper_level": paper, "ink_level": ink,
            "legibility_method": diagnostics.LEGIBILITY_METHOD,
        })
        mask_relative = diagnostics.mask_path(self.page_id)
        mask_hash = diagnostics.save_mask(mask, out_root / mask_relative)
        report = diagnostics.document(
            pixels, mask, page, image_sha256=page["image"]["sha256"], mask_sha256=mask_hash
        )
        ranks = {"readable": 0, "uncertain": 1, "illegible": 2}
        by_id = {word["id"]: word for word in self.words}
        for word in self.words:
            word["legibility"] = report["words"][word["id"]]["legibility"]
        for line in self.lines:
            line["legibility"] = max(
                (by_id[wid]["legibility"] for wid in line["word_ids"]), key=ranks.get
            )
        relative = diagnostics.diagnostics_path(self.page_id)
        write_json(out_root / relative, report)
        page["extensions"] = {"mf:diagnostics": {
            "version": "1", "path": relative, "sha256": sha256(out_root / relative),
            "mask_path": mask_relative, "mask_sha256": mask_hash,
        }}
        return page


def render_page(config: Config, index: int, assets: list[dict], out_root: Path) -> dict:
    return Composer(config, index, assets, out_root).finish(out_root)
