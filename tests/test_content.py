"""Tiny original text fixtures only: no corpus, image or rendering process."""

import hashlib
import json
import random
from copy import deepcopy
from pathlib import Path

import pytest

from mille_feuilles import content


def asset(identity="body-a", raw="Été.\n\nÎle.\n\nFin.", *, role="body", document=None):
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    return {
        "id": identity, "kind": "text", "path": f"texts/{identity}.txt",
        "sha256": hashlib.sha256(data).hexdigest(),
        "metadata": {"role": role, "source_document_id": document or f"doc-{identity}",
                     "source_group_id": "same-group"},
    }


def put(root, source, data):
    path = root / source["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return path


class Draws(random.Random):
    """Inspect the exact public draw contract without relying on lucky seeds."""

    def __init__(self, document=0, count=0, start=0):
        super().__init__(0)
        self.positions = iter((document, count))
        self.start = start
        self.calls = []

    def choice(self, values):
        self.calls.append(("choice", deepcopy(values)))
        return values[next(self.positions)]

    def randrange(self, stop):
        self.calls.append(("randrange", stop))
        assert 0 <= self.start < stop
        return self.start


def test_index_reports_all_documents_sorted_and_only_indexes_eligible():
    values = [
        (asset("z", "Un seul."), "Un seul."),
        (asset("b", "Été.\n\nÎle."), "Été.\n\nÎle."),
        (asset("a", "Matin.\n\nMidi.\n\nSoir."), "Matin.\n\nMidi.\n\nSoir."),
        (asset("empty", " \n\t"), " \n\t"),
    ]
    index = content.index_body_documents(values)
    assert [doc["asset"]["id"] for doc in index["documents"]] == ["a", "b"]
    report = index["report"]
    assert set(report) == {"version", "profile", "calibrated", "documents"}
    assert (report["version"], report["profile"], report["calibrated"]) == (
        "1", "consecutive-v1", False,
    )
    assert report["documents"] == [
        {"asset_id": identity, "source_document_id": f"doc-{identity}",
         "sha256": next(a["sha256"] for a, _ in values if a["id"] == identity),
         "unit_count": size, "eligible": size >= 2,
         "reason": None if size >= 2 else "fewer_than_two_body_units"}
        for identity, size in (("a", 3), ("b", 2), ("empty", 0), ("z", 1))
    ]
    # No raw text or path leaks into the compact JSON-serializable receipt.
    assert "Matin." not in json.dumps(report)
    assert all(set(row) == {"asset_id", "source_document_id", "sha256", "unit_count",
                            "eligible", "reason"} for row in report["documents"])


def test_unicode_offsets_original_separators_and_last_admissible_start():
    raw = "  Écho naïf.\nLigne liée.  \n\nDeuxième été.\n\nFin déjà.\n\nDernier quai.  \n"
    index = content.index_body_documents([(asset(raw=raw), raw)])
    draws = Draws(count=0, start=2)
    chosen = content.choose_body_sequence(index, draws)
    assert chosen["unit_range"] == [2, 4]
    assert chosen["start"] == raw.index("Fin déjà.")
    assert chosen["end"] == len(raw) - 1
    assert chosen["text"] == "Fin déjà.\n\nDernier quai.  "
    assert draws.calls[1:] == [("choice", [2, 3]), ("randrange", 3)]
    # Byte offsets differ for accented text; the contract uses code points.
    assert chosen["start"] != len(raw[:chosen["start"]].encode("utf-8"))


def test_duplicate_unit_text_keeps_exact_window_offsets():
    raw = "Été.\n\nÉté.\n\nÉté."
    index = content.index_body_documents([(asset(raw=raw), raw)])
    chosen = content.choose_body_sequence(index, Draws(start=1))
    assert chosen["unit_range"] == [1, 3]
    assert (chosen["start"], chosen["end"], chosen["text"]) == (6, 16, "Été.\n\nÉté.")


def test_equal_text_in_distinct_documents_is_not_deduplicated_or_joined():
    raw = "Matin.\n\nSoir."
    sources = [asset("a", raw), asset("b", raw)]
    index = content.index_body_documents([(source, raw) for source in sources])
    for position, source in enumerate(sources):
        draws = Draws(document=position)
        chosen = content.choose_body_sequence(index, draws)
        assert chosen["source"] == source
        assert chosen["text"] == raw
        assert chosen["unit_range"] == [0, 2]
        assert len(draws.calls[0][1]) == 2
        assert draws.calls[1:] == [("choice", [2]), ("randrange", 1)]


def test_three_units_are_not_reduced_and_sampling_does_not_modify_index():
    raw = "Début.\n\nCentre.\n\nSuite.\n\nDernière."
    index = content.index_body_documents([(asset(raw=raw), raw)])
    original = deepcopy(index)
    chosen = content.choose_body_sequence(index, Draws(count=1, start=1))
    assert chosen["text"] == "Centre.\n\nSuite.\n\nDernière."
    assert chosen["unit_range"] == [1, 4]
    chosen["source"]["metadata"]["source_document_id"] = "mutation"
    assert index == original


def test_input_order_has_no_effect_and_source_metadata_is_not_aliased():
    a, b = asset("a"), asset("b")
    raw = "Été.\n\nÎle.\n\nFin."
    first = content.index_body_documents([(b, raw), (a, raw)])
    second = content.index_body_documents([(a, raw), (b, raw)])
    assert first == second
    a["metadata"]["source_document_id"] = "mutated-after-index"
    assert first == second
    assert content.choose_body_sequence(first, random.Random(381)) == content.choose_body_sequence(
        second, random.Random(381),
    )


def test_rng_sequence_is_document_count_start_and_global_state_stays_intact():
    short, long = "Court.\n\nEntier.", "Aube.\n\nMidi.\n\nSoir.\n\nNuit."
    index = content.index_body_documents([(asset("a", short), short), (asset("z", long), long)])
    initial_global = random.getstate()
    actual, expected = random.Random(726), random.Random(726)
    for _ in range(20):
        doc = expected.choice(index["documents"])
        size = expected.choice([2] if len(doc["units"]) == 2 else [2, 3])
        start = expected.randrange(len(doc["units"]) - size + 1)
        chosen = content.choose_body_sequence(index, actual)
        assert chosen["source"] == doc["asset"]
        assert chosen["unit_range"] == [start, start + size]
        assert actual.getstate() == expected.getstate()
    assert random.getstate() == initial_global


@pytest.mark.parametrize("rng", [random, random.SystemRandom(), None, object()])
def test_nonlocal_or_nondeterministic_rng_is_refused_without_global_consumption(rng):
    raw = "Début.\n\nFin."
    index = content.index_body_documents([(asset(raw=raw), raw)])
    state = random.getstate()
    with pytest.raises(ValueError, match="local deterministic random.Random"):
        content.choose_body_sequence(index, rng)
    assert random.getstate() == state


@pytest.mark.parametrize("raw", ["", " \n\t", "Un seul paragraphe.", "Une ligne.\nLiée."])
def test_no_eligible_body_is_a_controlled_refusal(raw):
    with pytest.raises(ValueError, match="at least two units"):
        content.index_body_documents([(asset(raw=raw), raw)])


@pytest.mark.parametrize("mode", ["asset", "document"])
def test_duplicate_id_is_rejected_even_when_text_differs(mode):
    left, right = asset("a"), asset("b")
    if mode == "asset":
        right["id"] = left["id"]
    else:
        right["metadata"]["source_document_id"] = left["metadata"]["source_document_id"]
    with pytest.raises(ValueError, match="duplicate"):
        content.index_body_documents([(left, "Gauche.\n\nFin."), (right, "Droite.\n\nFin.")])


@pytest.mark.parametrize("raw,reason", [
    ("E\u0301te\u0301.\n\nFin.", "NFC"),
    ("Début.\r\n\r\nFin.", "universal-newline"),
    (b"Start.\n\nEnd.", "must be text"),
])
def test_pure_helper_requires_already_decoded_nfc_text(raw, reason):
    with pytest.raises(ValueError, match=reason):
        content.index_body_documents([(asset(), raw)])


@pytest.mark.parametrize("change", [
    lambda value: value.pop("id"),
    lambda value: value.update(sha256="0" * 64 + "\n"),
    lambda value: value["metadata"].pop("source_document_id"),
    lambda value: value["metadata"].update(role="title"),
])
def test_index_identity_is_checked(change):
    value = asset()
    change(value)
    with pytest.raises(ValueError):
        content.index_body_documents([(value, "Début.\n\nFin.")])


@pytest.mark.parametrize("value", [None, {}, [(asset(),)], [None]])
def test_index_bad_envelope_is_controlled(value):
    with pytest.raises(ValueError):
        content.index_body_documents(value)


def test_preflight_crlf_hashes_original_bytes_and_matches_path_read_text(tmp_path):
    original = "Été.\r\n\r\nÎle.\r\n\r\nFin.\r\n".encode()
    source = asset(raw=original)
    path = put(tmp_path, source, original)
    report = content.preflight_content(tmp_path, [source], profile=content.PROFILE)
    decoded = path.read_text(encoding="utf-8")
    assert decoded == "Été.\n\nÎle.\n\nFin.\n"
    index = content.index_body_documents([(source, decoded)])
    assert report == index["report"]
    chosen = content.choose_body_sequence(index, Draws(start=1))
    assert (chosen["start"], chosen["end"], chosen["text"]) == (6, 16, "Île.\n\nFin.")
    assert source["sha256"] != hashlib.sha256(decoded.encode()).hexdigest()
    assert path.read_bytes() == original


def test_preflight_ignores_unselected_files_and_does_not_open_other_roles(tmp_path, monkeypatch):
    text = "Notre début.\n\nNotre fin."
    body = asset(raw=text)
    path = put(tmp_path, body, text)
    (tmp_path / "unselected.txt").write_bytes(b"invalid utf8 \xff")
    title, ad = asset("title", role="title"), asset("ad", role="advertisement")
    title["path"], ad["path"] = "../not-a-source", "/also-not-a-source"
    title["sha256"] = ad["sha256"] = "invalid-unused-sha"
    font = {"kind": "font", "path": "missing-font"}
    opened = []
    original_open = Path.open

    def observe(self, *args, **kwargs):
        opened.append(self)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observe)
    report = content.preflight_content(tmp_path, [ad, body, font, title], profile=content.PROFILE)
    assert opened == [path.resolve()]
    assert [record["asset_id"] for record in report["documents"]] == [body["id"]]


@pytest.mark.parametrize("relative", ["../outside.txt", "/absolute.txt", "a\\b", "a//b", "./a"])
def test_preflight_refuses_unsafe_paths_before_read(tmp_path, relative):
    source = asset()
    source["path"] = relative
    with pytest.raises(ValueError, match="path"):
        content.preflight_content(tmp_path, [source], profile=content.PROFILE)
    assert list(tmp_path.iterdir()) == []


def test_preflight_refuses_symlink_escape(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("Texte extérieur.\n\nFin.", encoding="utf-8")
    (root / "escape.txt").symlink_to(outside)
    source = asset()
    source["path"] = "escape.txt"
    with pytest.raises(ValueError, match="escapes"):
        content.preflight_content(root, [source], profile=content.PROFILE)


@pytest.mark.parametrize("kind", ["sha", "utf8", "nfc", "missing", "directory"])
def test_preflight_bad_source_is_a_controlled_refusal_without_writing(tmp_path, kind):
    text = b"Bonjour.\n\nBonsoir."
    if kind == "utf8":
        text = b"Bonjour\xff.\n\nBonsoir."
    if kind == "nfc":
        text = "E\u0301te\u0301.\n\nFin.".encode()
    source = asset(raw=text)
    if kind not in {"missing", "directory"}:
        put(tmp_path, source, text)
    if kind == "sha":
        source["sha256"] = "0" * 64
    if kind == "directory":
        (tmp_path / source["path"]).mkdir(parents=True)
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    with pytest.raises(ValueError):
        content.preflight_content(tmp_path, [source], profile=content.PROFILE)
    assert sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")) == before


def test_preflight_no_eligible_document_does_not_create_output(tmp_path):
    body = asset(raw="Seul.")
    put(tmp_path, body, "Seul.")
    destination = tmp_path / "output-never-used"
    with pytest.raises(ValueError, match="at least two units"):
        content.preflight_content(tmp_path, [body], profile=content.PROFILE)
        destination.mkdir()
    assert not destination.exists()


def test_unknown_profile_refused_before_source_access(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("unknown profile attempted file I/O")

    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(ValueError, match="unknown profile"):
        content.preflight_content(tmp_path, [asset()], profile="not-a-profile")


@pytest.mark.parametrize("limit", ["document_bytes", "total_text_bytes", "documents"])
def test_preflight_reuses_catalog_limits_with_tiny_inputs(tmp_path, monkeypatch, limit):
    from mille_feuilles.catalog import LIMITS

    raw = "Début.\n\nFin."
    source = asset(raw=raw)
    put(tmp_path, source, raw)
    # Shrink the limit for this fixture; never expand production budgets.
    monkeypatch.setitem(LIMITS, limit, 0 if limit == "documents" else 4)
    with pytest.raises(ValueError, match="budget"):
        content.preflight_content(tmp_path, [source], profile=content.PROFILE)
