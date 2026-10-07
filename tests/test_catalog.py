"""Multi-document import: verified rights, safe identity, duplicates and exclusions.

Every text below is an original fixture written for these tests; no corpus is read.
"""

import hashlib
import json
import os
import secrets
import unicodedata
from pathlib import Path

import pytest

from mille_feuilles import catalog as cat
from mille_feuilles.catalog import (
    CatalogError,
    import_texts,
    load_catalog,
    ngram_digests,
    text_assets_by_role,
    text_units,
    validate_catalog,
)
from mille_feuilles.io import ROOT
from mille_feuilles.render import text_segments

WORDS = (
    "matin soir rue place marché pont quai jardin conseil maire séance théâtre "
    "voyageur gare lettre nouvelle récolte vigne orage fête musique école port "
    "navire foire hôtel préfet budget canal moulin forêt chemin village"
).split()


def prose(seed: str, paragraphs: int = 2, words: int = 24) -> str:
    """Deterministic original French-like prose, distinct for each seed."""
    digest = hashlib.sha256(seed.encode()).digest()
    out = []
    for p in range(paragraphs):
        chosen = [WORDS[(digest[(p * words + i) % 32] + i * 7 + p) % len(WORDS)] for i in range(words)]
        out.append(f"Le {seed} : " + " ".join(chosen) + ", fin.")
    return "\n\n".join(out) + "\n"


def titles(seed: str) -> str:
    return f"Chronique {seed}\nNouvelles {seed}\n"


NOTICE = "Texte original écrit pour les tests Mille Feuilles, dédié au domaine public (CC0-1.0).\n"


def row(path, role, doc, group, **extra):
    value = {
        "path": path,
        "role": role,
        "source_document_id": doc,
        "source_group_id": group,
        "language": "fr",
        "source_uri": f"urn:mf-test:{doc}",
        "rights": {
            "status": "verified",
            "license": "CC0-1.0",
            "evidence_path": "NOTICE.txt",
            "attribution": "Mille Feuilles tests",
            "redistribution_allowed": True,
        },
    }
    value.update(extra)
    return value


def make_source(directory: Path, docs: list[tuple[str, str, str, str]], rows_extra=None, raw_lines=()):
    """docs: (doc_id, group, role, text). Returns the manifest path."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "NOTICE.txt").write_text(NOTICE, encoding="utf-8")
    lines = []
    for index, (doc, group, role, text) in enumerate(docs):
        name = f"doc{index:03d}.txt"
        (directory / name).write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
        value = row(name, role, doc, group)
        if rows_extra and doc in rows_extra:
            rows_extra[doc](value)
        lines.append(json.dumps(value, ensure_ascii=False))
    lines.extend(raw_lines)
    manifest = directory / "import.jsonl"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def standard_docs(prefix="", groups=("g1", "g2")):
    docs = []
    for group in groups:
        docs += [
            (f"{prefix}{group}-body-a", group, "body", prose(f"{prefix}{group}a")),
            (f"{prefix}{group}-body-b", group, "body", prose(f"{prefix}{group}b")),
            (f"{prefix}{group}-titles", group, "title", titles(f"{prefix}{group}")),
            (f"{prefix}{group}-ads", group, "advertisement", prose(f"{prefix}{group}ad", 2, 10)),
        ]
    return docs


def files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def digests(root: Path) -> set[str]:
    return {hashlib.sha256(data).hexdigest() for data in files(root).values()}


def test_import_builds_valid_self_contained_bundle_without_demo_texts(tmp_path):
    manifest = make_source(tmp_path / "src", standard_docs())
    bundle = tmp_path / "bundle"
    report = import_texts(manifest, bundle)
    assert report["status"] == "pass", report
    assert len(report["accepted"]) == 8 and report["rejected"] == []
    catalog = load_catalog(bundle)
    assert catalog["schema_version"] == "0.3.0"
    assert validate_catalog(bundle) == []
    by_role = text_assets_by_role(catalog)
    assert [len(by_role[r]) for r in ("body", "title", "advertisement")] == [4, 2, 2]
    # Fonts and their evidence are copied, the three demonstration texts are not.
    demo = [a for a in load_catalog(ROOT)["assets"] if a["kind"] == "text"]
    assert not {a["sha256"] for a in demo} & digests(bundle)
    for font in (a for a in catalog["assets"] if a["kind"] == "font"):
        assert (bundle / font["path"]).is_file()
        for evidence in font["metadata"]["evidence_files"]:
            assert (bundle / evidence["path"]).is_file()
    # Imported bytes are kept intact and catalogued by content hash.
    for asset in by_role["body"]:
        data = (bundle / asset["path"]).read_bytes()
        assert asset["path"] == f"assets/texts/imported/{hashlib.sha256(data).hexdigest()[:20]}.txt"
        assert asset["rights"]["evidence_uri"].startswith("assets/evidence/")
    assert json.loads((bundle / "assets/import-report.json").read_text()) == report


def test_without_exclusions_external_protection_is_explicitly_not_evaluated(tmp_path):
    report = import_texts(make_source(tmp_path / "src", standard_docs()), tmp_path / "b")
    assert report["external_protection"] == "NOT EVALUATED"
    assert {v["status"] for v in report["exclusions"].values()} == {"not_evaluated"}


def test_hostile_identifiers_never_shape_bundle_paths(tmp_path):
    docs = standard_docs()
    docs[0] = ("../../outside/évasion", "g1/../../x", "body", docs[0][3])
    bundle = tmp_path / "bundle"
    report = import_texts(make_source(tmp_path / "src", docs), bundle)
    assert report["status"] == "pass", report
    assert not (tmp_path / "outside").exists()
    for relative in files(bundle):
        assert "outside" not in relative and "évasion" not in relative and ".." not in relative
    assert validate_catalog(bundle) == []


def test_nonempty_bundle_is_refused_without_writing(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "keep.txt").write_text("x")
    with pytest.raises(CatalogError):
        import_texts(make_source(tmp_path / "src", standard_docs()), bundle)
    assert files(bundle) == {"keep.txt": b"x"}


def reject_one(tmp_path, mutate=None, text=None, name="bad"):
    """Import standard docs plus one faulty body document; return its rejection reasons."""
    docs = standard_docs() + [(name, "gbad", "body", text if text is not None else prose("bad"))]
    extra = {name: mutate} if mutate else None
    bundle = tmp_path / "bundle"
    report = import_texts(make_source(tmp_path / "src", docs, extra), bundle)
    assert report["status"] == "pass"
    rejected = [r for r in report["rejected"] if r["line"] == len(docs)]
    assert len(rejected) == 1 and len(report["rejected"]) == 1, report["rejected"]
    assert name not in {a["source_document_id"] for a in report["accepted"]}
    bad_bytes = (tmp_path / "src" / f"doc{len(docs) - 1:03d}.txt").read_bytes()
    assert hashlib.sha256(bad_bytes).hexdigest() not in digests(bundle)
    return " | ".join(rejected[0]["reasons"])


def _set(path, value):
    def apply(row):
        target = row
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return apply


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (_set(("rights", "status"), "unresolved"), "droits"),
        (_set(("rights", "redistribution_allowed"), False), "redistribution"),
        (_set(("rights", "evidence_path"), "missing.txt"), "absent"),
        (_set(("rights", "evidence_path"), "../NOTICE.txt"), "unsafe"),
        (_set(("rights", "license"), " "), "license"),
        (_set(("path",), "../doc000.txt"), "unsafe"),
        (_set(("path",), "/etc/hosts"), "unsafe"),
        (_set(("role",), "editorial"), "rôle"),
        (_set(("language",), "de"), "langue"),
        (_set(("date",), "7 mai 1884"), "date"),
        (_set(("historical_corpus",), "yes"), "booléen"),
        (_set(("source_group_id",), ""), "source_group_id"),
        (_set(("source_document_id",), "line\nbreak"), "source_document_id"),
        (_set(("unexpected",), 1), "champs inconnus"),
        (lambda row: row.pop("source_uri"), "champs manquants"),
    ],
)
def test_faulty_manifest_rows_are_rejected_without_cataloguing_bytes(tmp_path, mutate, expected):
    assert expected in reject_one(tmp_path, mutate)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("﻿" + prose("bom"), "BOM"),
        (unicodedata.normalize("NFD", prose("décomposé")), "NFC"),
        (prose("cr").replace("\n", "\r\n"), "retour chariot"),
        (prose("tab").replace(" ", "\t", 1), "tabulation"),
        (prose("ctl") + "​", "contrôle"),
        (prose("glyph") + "漢字\n", "glyphes absents"),
        ("\n\n  \n", "aucune unité"),
        (b"\xff\xfe pas utf-8", "UTF-8"),
    ],
)
def test_faulty_text_bytes_are_rejected(tmp_path, text, expected):
    assert expected in reject_one(tmp_path, text=text)


def test_empty_evidence_is_rejected(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "EMPTY.txt").write_text("  \n")
    assert "preuve" in reject_one(tmp_path, _set(("rights", "evidence_path"), "EMPTY.txt"))


def test_invalid_json_line_is_reported(tmp_path):
    manifest = make_source(tmp_path / "src", standard_docs(), raw_lines=['{"path": "x", "path": "y"}', "[1]", "{"])
    report = import_texts(manifest, tmp_path / "b")
    assert report["status"] == "pass"
    assert len(report["rejected"]) == 3 and all(r["source_document_id"] is None for r in report["rejected"])


def test_duplicate_document_ids_and_contents_reject_every_occurrence(tmp_path):
    docs = standard_docs() + [
        ("dup-id", "gx", "body", prose("x1")),
        ("dup-id", "gy", "body", prose("x2")),
        ("same-a", "gz", "body", prose("same")),
        ("same-b", "gw", "advertisement", prose("same")),
    ]
    report = import_texts(make_source(tmp_path / "src", docs), tmp_path / "b")
    rejected = sorted(r["source_document_id"] for r in report["rejected"])
    assert rejected == ["dup-id", "dup-id", "same-a", "same-b"]
    accepted = {a["source_document_id"] for a in report["accepted"]}
    assert not accepted & set(rejected)


def test_missing_role_after_rejections_fails_without_catalog(tmp_path):
    docs = [d for d in standard_docs() if d[2] != "title"]
    docs.append(("t", "g9", "title", "漢字\n"))
    bundle = tmp_path / "b"
    report = import_texts(make_source(tmp_path / "src", docs), bundle)
    assert report["status"] == "fail" and report["missing_roles"] == ["title"]
    assert not (bundle / "assets/catalog.json").exists()
    assert (bundle / "assets/import-report.json").is_file()


def test_manifest_order_does_not_change_catalog_bytes(tmp_path):
    docs = standard_docs(groups=("g1", "g2", "g3"))
    one = import_texts(make_source(tmp_path / "s1", docs), tmp_path / "b1")
    two = import_texts(make_source(tmp_path / "s2", list(reversed(docs))), tmp_path / "b2")
    assert one["accepted"] == two["accepted"]
    assert (tmp_path / "b1/assets/catalog.json").read_bytes() == (tmp_path / "b2/assets/catalog.json").read_bytes()


def test_document_size_limit(tmp_path, monkeypatch):
    monkeypatch.setitem(cat.LIMITS, "document_bytes", 400)
    assert "volumineux" in reject_one(tmp_path, text="Le long " + "texte " * 200 + "\n")


# --- exclusions ------------------------------------------------------------


def ngram_file(path: Path, texts: list[str], n=8, **override) -> Path:
    salt = secrets.token_bytes(16)
    hashes = sorted(set().union(*(ngram_digests(t, n, salt) for t in texts)))
    value = {
        "format": "mille-feuilles-ngram-exclusions", "version": "1", "n": n,
        "normalization": "nfc-casefold-word-v1", "salt_hex": salt.hex(),
        "digest": "sha256-128", "hashes": hashes,
    }
    value.update(override)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_document_exclusions_match_document_group_or_uri(tmp_path):
    docs = standard_docs(groups=("g1", "g2", "g3"))
    keys = tmp_path / "exclude.txt"
    keys.write_text("# protégés\ng1-body-a\ng2\n\nurn:mf-test:g3-ads\n", encoding="utf-8")
    report = import_texts(make_source(tmp_path / "src", docs), tmp_path / "b", {"documents": keys, "ngrams": None})
    rejected = {r["source_document_id"] for r in report["rejected"]}
    assert rejected == {"g1-body-a", "g2-body-a", "g2-body-b", "g2-titles", "g2-ads", "g3-ads"}
    assert report["exclusions"]["documents"]["status"] == "evaluated"
    assert report["exclusions"]["documents"]["entries"] == 3
    assert report["external_protection"] == "NOT EVALUATED"


def test_one_protected_ngram_rejects_the_whole_document(tmp_path):
    docs = standard_docs()
    protected = docs[1][3].split("\n\n")[1]  # one paragraph of g1-body-b
    words = protected.split()
    window = " ".join(words[3:11]).upper()  # casefold and punctuation are normalized
    ngrams = ngram_file(tmp_path / "ngrams.json", [window])
    keys = tmp_path / "none.txt"
    keys.write_text("")
    report = import_texts(make_source(tmp_path / "src", docs), tmp_path / "b",
                          {"documents": keys, "ngrams": ngrams})
    assert [r["source_document_id"] for r in report["rejected"]] == ["g1-body-b"]
    assert report["external_protection"] == "evaluated"
    assert report["exclusions"]["ngrams"]["n"] == 8
    # The source bytes of the other documents are untouched in the bundle.
    accepted = {a["source_document_id"]: a for a in report["accepted"]}
    assert accepted["g1-body-a"]["sha256"] == hashlib.sha256(docs[0][3].encode()).hexdigest()


@pytest.mark.parametrize(
    "override",
    [
        {"format": "other"},
        {"version": "2"},
        {"normalization": "hipe"},
        {"digest": "sha1"},
        {"n": 2},
        {"salt_hex": "00"},
        {"hashes": ["XYZ"]},
        {"hashes": ["b" * 32, "a" * 32]},
        {"hashes": ["a" * 32, "a" * 32]},
        {"extra": True},
    ],
)
def test_malformed_ngram_exclusions_stop_before_any_write(tmp_path, override):
    path = ngram_file(tmp_path / "ngrams.json", ["un deux trois quatre cinq six sept huit"], **override)
    bundle = tmp_path / "bundle"
    with pytest.raises(CatalogError):
        import_texts(make_source(tmp_path / "src", standard_docs()), bundle, {"ngrams": path})
    assert not bundle.exists()


def test_unknown_exclusion_key_is_refused(tmp_path):
    with pytest.raises(CatalogError):
        import_texts(make_source(tmp_path / "src", standard_docs()), tmp_path / "b", {"tests": None})


def test_invalid_document_exclusion_key_stops_before_write(tmp_path):
    keys = tmp_path / "exclude.txt"
    keys.write_text(" leading-space\n", encoding="utf-8")
    with pytest.raises(CatalogError):
        import_texts(make_source(tmp_path / "src", standard_docs()), tmp_path / "b", {"documents": keys})
    assert not (tmp_path / "b").exists()


def test_ngram_digest_normalization_is_documented_behaviour():
    salt = b"s" * 16
    assert ngram_digests("Été, à PARIS: le soir", 3, salt) == ngram_digests("été à paris le soir", 3, salt)
    assert ngram_digests("deux mots", 3, salt) == set()


# --- catalog validation ------------------------------------------------------


def test_text_units_match_renderer_segments_on_embedded_texts():
    for asset in load_catalog(ROOT)["assets"]:
        if asset["kind"] == "text" and asset["metadata"]["role"] != "title":
            path = ROOT / asset["path"]
            assert text_units(path.read_text(encoding="utf-8"), asset["metadata"]["role"]) == text_segments(path)


def test_embedded_020_catalog_stays_valid():
    catalog = load_catalog(ROOT)
    assert catalog["schema_version"] == "0.2.0"
    assert validate_catalog(ROOT) == []


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "bundle"
    assert import_texts(make_source(tmp_path / "src", standard_docs()), root)["status"] == "pass"
    return root


def test_tampered_imported_text_is_detected(bundle):
    asset = text_assets_by_role(load_catalog(bundle))["body"][0]
    path = bundle / asset["path"]
    os.chmod(path, 0o644)
    path.write_text(path.read_text(encoding="utf-8") + "ajout\n", encoding="utf-8")
    assert any("empreinte" in e for e in validate_catalog(bundle))


def test_missing_evidence_is_detected(bundle):
    asset = text_assets_by_role(load_catalog(bundle))["title"][0]
    (bundle / asset["metadata"]["evidence_files"][0]["path"]).unlink()
    assert any("preuve" in e for e in validate_catalog(bundle))


@pytest.mark.parametrize("field", ["source_group_id", "role", "language", "evidence_files"])
def test_030_schema_requires_text_metadata(bundle, field):
    catalog = load_catalog(bundle)
    next(a for a in catalog["assets"] if a["kind"] == "text")["metadata"].pop(field)
    assert validate_catalog(bundle, catalog)


def test_duplicate_source_document_in_catalog_is_detected(bundle):
    catalog = load_catalog(bundle)
    texts = [a for a in catalog["assets"] if a["kind"] == "text"]
    texts[1]["metadata"]["source_document_id"] = texts[0]["metadata"]["source_document_id"]
    assert any("source_document_id dupliqué" in e for e in validate_catalog(bundle, catalog))


def _verify_assets():
    import importlib.util

    spec = importlib.util.spec_from_file_location("verify_assets", ROOT / "assets/verify_assets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify


def test_standalone_verifier_accepts_imported_bundle_and_detects_tampering(bundle):
    verify = _verify_assets()
    report = verify(bundle)
    assert report["status"] == "pass", report["errors"]
    assert report["schema_version"] == "0.3.0"
    assert {f["id"] for f in report["fonts"] if f["required_by_profile"]} == {
        "font_oldstandard_regular", "font_oldstandard_bold"
    }
    asset = text_assets_by_role(load_catalog(bundle))["advertisement"][0]
    (bundle / asset["path"]).write_text("altéré\n", encoding="utf-8")
    assert verify(bundle)["status"] == "fail"


# --- independent review of lot 2 ----------------------------------------------


def test_crossed_id_and_content_duplicates_reject_every_occurrence(tmp_path):
    # A and B share an id; C shares A's bytes under another id: all three go.
    docs = standard_docs() + [
        ("dup", "ga", "body", prose("X")),
        ("dup", "gb", "body", prose("Y")),
        ("other", "gc", "body", prose("X")),
    ]
    report = import_texts(make_source(tmp_path / "src", docs), tmp_path / "b")
    assert sorted(r["source_document_id"] for r in report["rejected"]) == ["dup", "dup", "other"]
    assert not {"dup", "other"} & {a["source_document_id"] for a in report["accepted"]}


def test_duplicate_of_an_otherwise_rejected_row_is_still_ambiguous(tmp_path):
    docs = standard_docs() + [("twin", "ga", "body", prose("t1")), ("twin", "gb", "body", prose("t2"))]
    extra = {"twin": _set(("rights", "status"), "unresolved")}
    # Both "twin" rows get unresolved rights; the first is then restored, so
    # one twin is otherwise valid and the other is rejected for its rights.
    manifest = make_source(tmp_path / "src", docs, extra)
    lines = manifest.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[-2])
    first["rights"]["status"] = "verified"
    lines[-2] = json.dumps(first, ensure_ascii=False)
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = import_texts(manifest, tmp_path / "b")
    twins = [r for r in report["rejected"] if r["source_document_id"] == "twin"]
    assert len(twins) == 2
    assert all(any("dupliqué" in reason for reason in r["reasons"]) for r in twins)


def test_import_volume_limit_stops_before_any_write(tmp_path, monkeypatch):
    monkeypatch.setitem(cat.LIMITS, "total_text_bytes", 300)
    bundle = tmp_path / "b"
    with pytest.raises(CatalogError, match="volume total"):
        import_texts(make_source(tmp_path / "src", standard_docs()), bundle)
    assert not bundle.exists()


def test_evidence_entry_without_sha256_is_an_error_not_an_exception():
    catalog = load_catalog(ROOT)
    text = next(a for a in catalog["assets"] if a["kind"] == "text")
    text["metadata"]["evidence_files"] = [{"path": text["metadata"]["evidence_files"][0]["path"]}]
    errors = validate_catalog(ROOT, catalog)
    assert any("preuve mal formée" in e for e in errors)


def test_030_text_requires_hashed_local_evidence(bundle):
    catalog = load_catalog(bundle)
    text = next(a for a in catalog["assets"] if a["kind"] == "text")
    text["metadata"]["evidence_files"] = []
    assert validate_catalog(bundle, catalog)
    catalog = load_catalog(bundle)
    text = next(a for a in catalog["assets"] if a["kind"] == "text")
    # A local evidence_uri that exists but is not hashed is refused in 0.3.0.
    text["rights"]["evidence_uri"] = "assets/import-report.json"
    errors = validate_catalog(bundle, catalog)
    assert any("evidence_uri local absent des preuves hachées" in e for e in errors)
