"""Serialize hand-specified canonical fixture pages (every value below is written by hand).

Usage: python make_canonical.py OUTPUT_DIR
Writes fixture-1-order.json, fixture-2-unicode-hyphen-geometry.json, fixture-3-free-block.json.
"""
import json
import sys
from copy import deepcopy
from pathlib import Path


def box(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def page_from(words, lines, blocks, articles, order, unordered, spans, template_articles, size=(400, 300)):
    page = {
        "schema_version": "0.3.0", "page_id": "p", "profile": "fr_press_19c_columns_4_6",
        "image": {"path": "images/p.png", "sha256": "0" * 64, "width": size[0], "height": size[1],
                  "color_mode": "L", "dpi": 150},
        "language": "fr",
        "provenance": {"seed": 0, "template_id": "template_press_v1",
                       "asset_ids": ["template_press_v1", "text_fixture"], "text_spans": spans,
                       "parameters": {"columns": 4, "render_dpi": 150},
                       "extensions": {"mf:template_article_ids": template_articles}},
        "transforms": [], "articles": [], "blocks": [], "lines": [], "words": [], "reading_order": {},
    }
    for wid, lid, text, polygon, hyphenation in words:
        page["words"].append({"id": wid, "line_id": lid, "polygon": polygon, "text": text, "char_span": None,
                              "legibility": "readable", "hyphenation": hyphenation})
    for lid, bid, polygon, baseline in lines:
        ws = [w for w in page["words"] if w["line_id"] == lid]
        cursor, texts = 0, []
        for w in ws:
            w["char_span"] = [cursor, cursor + len(w["text"])]
            cursor += len(w["text"]) + 1
            texts.append(w["text"])
        page["lines"].append({"id": lid, "block_id": bid, "polygon": polygon, "baseline": baseline,
                              "text": " ".join(texts), "word_ids": [w["id"] for w in ws],
                              "legibility": "readable"})
    for bid, category, aid, polygon in blocks:
        page["blocks"].append({"id": bid, "category": category, "polygon": polygon, "article_id": aid,
                               "line_ids": [line["id"] for line in page["lines"] if line["block_id"] == bid]})
    for aid, block_ids in articles:
        page["articles"].append({"id": aid, "block_ids": block_ids})
    page["reading_order"] = {
        "block_ids": order, "unordered_block_ids": unordered,
        "line_ids": [lid for bid in order for lid in next(b for b in page["blocks"] if b["id"] == bid)["line_ids"]],
    }
    return page


def span(start, end, article, blocks):
    return {"asset_id": "text_fixture", "start": start, "end": end, "source_document_id": "fixture",
            "article_id": article, "block_ids": blocks}


# Fixture 1 — reading order differs from identifier order; the advertisement is in the MIDDLE
# (rank 2 of 5), between two ordinary text regions.
F1 = dict(
    words=[
        ("p_w000000", "p_l00000", "MILLE", box(10, 10, 90, 30), None),
        ("p_w000001", "p_l00000", "FEUILLES", box(100, 10, 200, 30), None),
        ("p_w000002", "p_l00001", "Chronique", box(210, 50, 310, 70), None),
        ("p_w000003", "p_l00002", "Le", box(210, 80, 230, 95), None),
        ("p_w000004", "p_l00002", "conseil", box(236, 80, 296, 95), None),
        ("p_w000005", "p_l00002", "a", box(302, 80, 312, 95), None),
        ("p_w000006", "p_l00003", "voté.", box(210, 100, 252, 115), None),
        ("p_w000007", "p_l00004", "Vente", box(10, 80, 60, 95), None),
        ("p_w000008", "p_l00004", ":", box(64, 80, 68, 95), None),
        ("p_w000009", "p_l00004", "bois.", box(72, 80, 112, 95), None),
        ("p_w000010", "p_l00005", "Le", box(10, 50, 25, 65), None),
        ("p_w000011", "p_l00005", "marché", box(30, 50, 80, 65), None),
        ("p_w000012", "p_l00005", "ouvre.", box(85, 50, 130, 65), None),
    ],
    lines=[
        ("p_l00000", "p_b0000", box(10, 10, 200, 30), [[10, 26], [200, 26]]),
        ("p_l00001", "p_b0001", box(210, 50, 310, 70), [[210, 66], [310, 66]]),
        ("p_l00002", "p_b0002", box(210, 80, 312, 95), [[210, 92], [312, 92]]),
        ("p_l00003", "p_b0002", box(210, 100, 252, 115), [[210, 112], [252, 112]]),
        ("p_l00004", "p_b0003", box(10, 80, 112, 95), [[10, 92], [112, 92]]),
        ("p_l00005", "p_b0004", box(10, 50, 130, 65), [[10, 62], [130, 62]]),
    ],
    blocks=[
        ("p_b0000", "titre", "p_a0000", box(10, 10, 200, 30)),
        ("p_b0001", "titre", "p_a0001", box(210, 50, 310, 70)),
        ("p_b0002", "texte", "p_a0001", box(210, 80, 312, 115)),
        ("p_b0003", "annonce", "p_a0002", box(10, 80, 112, 95)),
        ("p_b0004", "texte", "p_a0003", box(10, 50, 130, 65)),
        ("p_b0005", "separateur", None, box(199, 40, 201, 140)),
    ],
    articles=[("p_a0000", ["p_b0000"]), ("p_a0001", ["p_b0001", "p_b0002"]),
              ("p_a0002", ["p_b0003"]), ("p_a0003", ["p_b0004"])],
    order=["p_b0000", "p_b0004", "p_b0003", "p_b0001", "p_b0002"],
    unordered=["p_b0005"],
    # Offsets into source-fixture-1.txt (written by hand; see SPEC.md § 0).
    spans=[span(0, 9, "p_a0001", ["p_b0001"]), span(10, 28, "p_a0001", ["p_b0002"]),
           span(29, 42, "p_a0002", ["p_b0003"]), span(43, 59, "p_a0003", ["p_b0004"])],
    template_articles=["p_a0000"],
)

# Fixture 2 — NFC Unicode, XML escaping, a hyphenation group across lines, and fractional,
# non-rectangular geometry that exercises the floor(v + 0.5) rounding rule.
H = "dissolution"
F2 = dict(
    words=[
        ("p_w000000", "p_l00000", "Œuvres", box(10, 10, 70, 30), None),
        ("p_w000001", "p_l00000", "d’été", box(76, 10, 120, 30), None),
        ("p_w000002", "p_l00000", "«", box(126, 10, 134, 30), None),
        ("p_w000003", "p_l00000", "Ponts", box(140, 10, 184, 30), None),
        ("p_w000004", "p_l00000", "&", box(190, 10, 200, 30), None),
        ("p_w000005", "p_l00000", "chaussées", box(206, 10, 286, 30), None),
        ("p_w000006", "p_l00000", "»", box(292, 10, 300, 30), None),
        ("p_w000007", "p_l00000", "—", box(306, 10, 326, 30), None),
        ("p_w000008", "p_l00001", "La", [[10.5, 50.49], [30.49, 50.0], [30.5, 65.5], [10.49, 66.0]], None),
        ("p_w000009", "p_l00001", "disso-", box(36.25, 50.0, 90.75, 66.0),
         {"group_id": "p_h00000", "part": "start", "reconstructed_text": H}),
        ("p_w000010", "p_l00002", "lution", box(10.0, 70.0, 60.5, 86.0),
         {"group_id": "p_h00000", "part": "end", "reconstructed_text": H}),
        ("p_w000011", "p_l00002", "du", box(66.0, 70.0, 84.0, 86.0), None),
        ("p_w000012", "p_l00002", "conseil.", box(90.0, 70.0, 150.4, 86.0), None),
    ],
    lines=[
        ("p_l00000", "p_b0000", box(10, 10, 326, 30), [[10, 26], [326, 26]]),
        ("p_l00001", "p_b0001", box(10.49, 50.0, 90.75, 66.0), [[10.49, 62.5], [90.75, 62.5]]),
        # A three-point baseline (polyline), fractional.
        ("p_l00002", "p_b0001", box(10.0, 70.0, 150.4, 86.0), [[10.0, 82.49], [80.5, 82.0], [150.4, 82.49]]),
    ],
    blocks=[
        ("p_b0000", "titre", "p_a0001", box(10, 10, 326, 30)),
        ("p_b0001", "texte", "p_a0001", box(10.0, 50.0, 150.4, 86.0)),
    ],
    articles=[("p_a0001", ["p_b0000", "p_b0001"])],
    order=["p_b0000", "p_b0001"], unordered=[],
    # Offsets into source-fixture-2.txt; "disso-"/"lution" rejoin to "dissolution".
    spans=[span(0, 36, "p_a0001", ["p_b0000"]), span(37, 63, "p_a0001", ["p_b0001"])],
    template_articles=[],
)


def fixture_3():
    """Fixture 1 with the ordinary block p_b0004 detached from any article (historical free block)."""
    spec = deepcopy(F1)
    spec["blocks"] = [(b, c, None if b == "p_b0004" else a, p) for b, c, a, p in spec["blocks"]]
    spec["articles"] = [a for a in spec["articles"] if a[0] != "p_a0003"]
    spec["spans"] = [{k: v for k, v in s.items() if k not in ("article_id", "block_ids")} for s in spec["spans"]]
    return spec


def as_v02(page):
    """0.2.0 canonical form: spans are not bound to articles; free textual blocks are allowed."""
    page["schema_version"] = "0.2.0"
    page["provenance"].pop("extensions", None)
    return page


def fixture_4():
    """Fixture 1 whose advertisement block is enlarged upward to overlap the ordinary block p_b0004
    (y 60..65). The canonical page stays valid; the profile must refuse the ambiguity."""
    spec = deepcopy(F1)
    spec["blocks"] = [(b, c, a, box(10, 60, 112, 95) if b == "p_b0003" else p) for b, c, a, p in spec["blocks"]]
    return spec


if __name__ == "__main__":
    out = Path(sys.argv[1])
    for name, spec in (("fixture-1-order", F1), ("fixture-2-unicode-hyphen-geometry", F2),
                       ("fixture-3-free-block", fixture_3()), ("fixture-4-advert-overlap", fixture_4())):
        page = page_from(**spec)
        if name == "fixture-3-free-block":
            page = as_v02(page)
        (out / f"{name}.json").write_text(json.dumps(page, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
