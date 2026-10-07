#!/usr/bin/env python3
"""Inventaire de fontes : licence déclarée, couverture de glyphes, traits OpenType.

Bibliothèque standard seulement (lecture directe des tables `name`, `cmap`,
`GSUB`) ; ne copie ni ne modifie aucune fonte. Usage :

    python3 tools/cadrage/fontes.py <fichier-ou-dossier> [...] > fontes.json

Pour chaque fichier .ttf/.otf : famille, style, version, licence (name 13/14),
présence d'un OFL.txt / LICENSE.txt à côté, SHA-256, et la part couverte de
chaque jeu de caractères ci-dessous. Une ligature sans point de code
(ct, st, ſt…) ne se voit que par les traits `liga`/`dlig`/`hlig` du GSUB :
leur présence est rapportée, pas le détail des substitutions.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

JEUX: dict[str, str] = {
    "ascii": "".join(chr(c) for c in range(0x20, 0x7F)),
    "francais": "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ«»’—–…°",
    "presse_xix": "½¼¾⅓⅔⅛⅜⅝⅞№§¶†‡‰£¢℔•※☞☛✝‖·×÷±ºª",
    "s_long": "ſ",
    "ligatures_unicode": "ﬀﬁﬂﬃﬄﬅﬆ",
    "ancien": "ꝑꝓꝗꝯꝰ⁊ẽõũĩñ̃ęǫꝭ",
}


def _tables(b: bytes) -> dict[str, tuple[int, int]]:
    n = struct.unpack(">H", b[4:6])[0]
    out = {}
    for i in range(n):
        tag, _, off, ln = struct.unpack(">4sIII", b[12 + 16 * i:28 + 16 * i])
        out[tag.decode("latin-1")] = (off, ln)
    return out


def _names(b: bytes, off: int) -> dict[int, str]:
    _, cnt, so = struct.unpack(">HHH", b[off:off + 6])
    out: dict[int, str] = {}
    for j in range(cnt):
        pid, eid, lid, nid, ln, o = struct.unpack(">HHHHHH", b[off + 6 + 12 * j:off + 18 + 12 * j])
        raw = b[off + so + o:off + so + o + ln]
        if pid == 3 and lid in (0x409, 0):
            out[nid] = raw.decode("utf-16-be", "replace")
        elif pid == 1 and nid not in out:
            out[nid] = raw.decode("mac-roman", "replace")
    return out


def _cmap(b: bytes, off: int) -> set[int]:
    _, n = struct.unpack(">HH", b[off:off + 4])
    cps: set[int] = set()
    for i in range(n):
        pid, eid, so = struct.unpack(">HHI", b[off + 4 + 8 * i:off + 12 + 8 * i])
        st = off + so
        fmt = struct.unpack(">H", b[st:st + 2])[0]
        if fmt == 4:
            segx2 = struct.unpack(">H", b[st + 6:st + 8])[0]
            ends = struct.unpack(f">{segx2 // 2}H", b[st + 14:st + 14 + segx2])
            starts = struct.unpack(f">{segx2 // 2}H", b[st + 16 + segx2:st + 16 + 2 * segx2])
            deltas = struct.unpack(f">{segx2 // 2}h", b[st + 16 + 2 * segx2:st + 16 + 3 * segx2])
            ro_off = st + 16 + 3 * segx2
            ros = struct.unpack(f">{segx2 // 2}H", b[ro_off:ro_off + segx2])
            for k, (s, e) in enumerate(zip(starts, ends)):
                for c in range(s, e + 1):
                    if c == 0xFFFF:
                        continue
                    if ros[k] == 0:
                        g = (c + deltas[k]) & 0xFFFF
                    else:
                        a = ro_off + 2 * k + ros[k] + 2 * (c - s)
                        g = struct.unpack(">H", b[a:a + 2])[0]
                        g = (g + deltas[k]) & 0xFFFF if g else 0
                    if g:
                        cps.add(c)
        elif fmt == 12:
            ng = struct.unpack(">I", b[st + 12:st + 16])[0]
            for k in range(ng):
                s, e, g = struct.unpack(">III", b[st + 16 + 12 * k:st + 28 + 12 * k])
                cps.update(range(s, e + 1))
    return cps


def _gsub_features(b: bytes, off: int) -> list[str]:
    fl = struct.unpack(">H", b[off + 6:off + 8])[0]
    base = off + fl
    n = struct.unpack(">H", b[base:base + 2])[0]
    return sorted({b[base + 2 + 6 * i:base + 6 + 6 * i].decode("latin-1") for i in range(n)})


def inspect(path: Path) -> dict:
    b = path.read_bytes()
    t = _tables(b)
    names = _names(b, t["name"][0]) if "name" in t else {}
    cps = _cmap(b, t["cmap"][0]) if "cmap" in t else set()
    feats = _gsub_features(b, t["GSUB"][0]) if "GSUB" in t else []
    lic_files = sorted(p.name for p in path.parent.iterdir()
                       if p.name.upper().startswith(("OFL", "LICENSE", "COPYING")))
    cov = {}
    for k, chars in JEUX.items():
        cs = [c for c in chars if not (0x300 <= ord(c) < 0x370)]
        miss = [c for c in cs if ord(c) not in cps]
        cov[k] = {"part": round(1 - len(miss) / len(cs), 3), "manquants": "".join(miss)}
    return {"fichier": str(path), "sha256": hashlib.sha256(b).hexdigest(),
            "famille": names.get(16) or names.get(1), "style": names.get(17) or names.get(2),
            "version": names.get(5), "copyright": (names.get(0) or "")[:200],
            "licence": (names.get(13) or "")[:160], "licence_url": names.get(14),
            "fichiers_licence_a_cote": lic_files, "glyphes_unicode": len(cps),
            "couverture": cov,
            "traits_ligatures": [f for f in feats if f in ("liga", "dlig", "hlig", "clig")],
            "autres_traits": [f for f in feats if f in ("smcp", "onum", "lnum", "swsh", "salt", "hist", "ss01", "ss02")]}


def main() -> int:
    out = []
    for arg in sys.argv[1:]:
        p = Path(arg).expanduser()
        files = [p] if p.is_file() else sorted(p.rglob("*.[ot]tf"))
        for f in files:
            try:
                out.append(inspect(f))
            except Exception as e:  # fonte illisible : signalée, pas ignorée
                out.append({"fichier": str(f), "erreur": repr(e)})
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
