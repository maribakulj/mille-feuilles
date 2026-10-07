"""Hand-typed expected PAGE geometry (integer points after floor(v + 0.5)), independent of any producer.

Each entry is typed by hand from SPEC.md § 5 applied to the canonical values; `b(x0, y0, x1, y1)` only
expands an axis-aligned rectangle into its four clockwise points. Usage: python make_expected_geometry.py DIR
"""
import json
import sys
from pathlib import Path


def b(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


F1 = {
    "regions": {"r_p_b0000": b(10, 10, 200, 30), "r_p_b0004": b(10, 50, 130, 65), "r_p_b0003": b(10, 80, 112, 95),
                "a_p_b0003": b(10, 80, 112, 95), "r_p_b0001": b(210, 50, 310, 70), "r_p_b0002": b(210, 80, 312, 115),
                "s_p_b0005": b(199, 40, 201, 140)},
    "lines": {"l_p_l00000": [b(10, 10, 200, 30), [[10, 26], [200, 26]]],
              "l_p_l00005": [b(10, 50, 130, 65), [[10, 62], [130, 62]]],
              "l_p_l00004": [b(10, 80, 112, 95), [[10, 92], [112, 92]]],
              "l_p_l00001": [b(210, 50, 310, 70), [[210, 66], [310, 66]]],
              "l_p_l00002": [b(210, 80, 312, 95), [[210, 92], [312, 92]]],
              "l_p_l00003": [b(210, 100, 252, 115), [[210, 112], [252, 112]]]},
    "words": {"w_p_w000000": ["MILLE", b(10, 10, 90, 30)], "w_p_w000001": ["FEUILLES", b(100, 10, 200, 30)],
              "w_p_w000002": ["Chronique", b(210, 50, 310, 70)], "w_p_w000003": ["Le", b(210, 80, 230, 95)],
              "w_p_w000004": ["conseil", b(236, 80, 296, 95)], "w_p_w000005": ["a", b(302, 80, 312, 95)],
              "w_p_w000006": ["voté.", b(210, 100, 252, 115)], "w_p_w000007": ["Vente", b(10, 80, 60, 95)],
              "w_p_w000008": [":", b(64, 80, 68, 95)], "w_p_w000009": ["bois.", b(72, 80, 112, 95)],
              "w_p_w000010": ["Le", b(10, 50, 25, 65)], "w_p_w000011": ["marché", b(30, 50, 80, 65)],
              "w_p_w000012": ["ouvre.", b(85, 50, 130, 65)]},
}
F2 = {
    "regions": {"r_p_b0000": b(10, 10, 326, 30), "r_p_b0001": b(10, 50, 150, 86)},
    "lines": {"l_p_l00000": [b(10, 10, 326, 30), [[10, 26], [326, 26]]],
              "l_p_l00001": [b(10, 50, 91, 66), [[10, 63], [91, 63]]],           # 10.49→10, 90.75→91, 62.5→63
              "l_p_l00002": [b(10, 70, 150, 86), [[10, 82], [81, 82], [150, 82]]]},  # three points; 80.5→81, 82.49→82
    "words": {"w_p_w000000": ["Œuvres", b(10, 10, 70, 30)], "w_p_w000001": ["d’été", b(76, 10, 120, 30)],
              "w_p_w000002": ["«", b(126, 10, 134, 30)], "w_p_w000003": ["Ponts", b(140, 10, 184, 30)],
              "w_p_w000004": ["&", b(190, 10, 200, 30)], "w_p_w000005": ["chaussées", b(206, 10, 286, 30)],
              "w_p_w000006": ["»", b(292, 10, 300, 30)], "w_p_w000007": ["—", b(306, 10, 326, 30)],
              "w_p_w000008": ["La", [[11, 50], [30, 50], [31, 66], [10, 66]]],  # non-rectangular quadrilateral
              "w_p_w000009": ["disso-", b(36, 50, 91, 66)],                     # 36.25→36, 90.75→91
              "w_p_w000010": ["lution", b(10, 70, 61, 86)],                     # 60.5→61
              "w_p_w000011": ["du", b(66, 70, 84, 86)],
              "w_p_w000012": ["conseil.", b(90, 70, 150, 86)]},                 # 150.4→150
}
if __name__ == "__main__":
    out = Path(sys.argv[1])
    for name, value in (("fixture-1-order", F1), ("fixture-2-unicode-hyphen-geometry", F2)):
        doc = {"format": "mille-feuilles-newseye-expected-geometry", "version": "1",
               "note": "Every Coords/Baseline point of the expected XML, typed by hand; Word text included.",
               **value}
        (out / f"{name}.expected-geometry.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                                                           encoding="utf-8")
