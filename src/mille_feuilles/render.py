"""Compose newspaper pages and annotations from the same font measurements.

Words are drawn individually at the recorded pen positions. The canonical text
is independent of glyph shaping; no OCR is used to recover annotations.
"""

from __future__ import annotations

import hashlib
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

    def as_dict(self) -> dict:
        value = asdict(self)
        if self.degradation_profile is None:
            del value["degradation_profile"]
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
        for role, documents in self.text_roles.items():
            units = []
            for source in documents:
                raw = (self.asset_root / source["path"]).read_text(encoding="utf-8")
                if unicodedata.normalize("NFC", raw) != raw:
                    raise ValueError(f"Texte source non NFC : {source['id']}")
                units.extend((source, text, start, end) for text, start, end in text_units(raw, role))
            if not units:
                raise ValueError(f"Au moins une unité de texte requise pour le rôle {role}")
            self.role_units[role] = units
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
        return page

    def _finish_measured(self, out_root: Path) -> dict:
        from . import degrade, diagnostics

        self.content()
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
        page["profile"] = PROFILE_MEASURED
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
