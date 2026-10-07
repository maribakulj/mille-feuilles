"""Import -> partition -> filtered generation, using original synthetic text.

These integration fixtures contain three small source groups and generate at
most one 800 x 1100 page per lot. Their combined real size is asserted below
20 MB. If the host falls below the production disk reserve, only these bounded
fixtures stub disk_usage; no real pilot or production guard is bypassed.
"""

from collections import Counter
from copy import deepcopy
import json
import shutil
import unicodedata

import pytest

from mille_feuilles import pipeline
from mille_feuilles.catalog import import_texts, load_catalog, validate_catalog
from mille_feuilles.io import sha256, write_json
from mille_feuilles.partition import assign_partitions, load_partition
from mille_feuilles.render import Config
from mille_feuilles.validation import load_json, validate_dataset, validate_page


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): sha256(path)
        for path in root.rglob("*") if path.is_file()
    }


def size_bytes(root):
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def normalized(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def composed_articles(page):
    """Independent reconstruction using declared article order and césures."""
    blocks = {item["id"]: item for item in page["blocks"]}
    lines = {item["id"]: item for item in page["lines"]}
    words = {item["id"]: item for item in page["words"]}
    results = []
    for article in page["articles"]:
        tokens = []
        for bid in article["block_ids"]:
            for lid in blocks[bid]["line_ids"]:
                for wid in lines[lid]["word_ids"]:
                    word = words[wid]
                    hyp = word["hyphenation"]
                    if hyp is None:
                        tokens.append(word["text"])
                    elif hyp["part"] == "start":
                        tokens.append(hyp["reconstructed_text"])
        results.append(" ".join(tokens))
    return results


@pytest.fixture(scope="module")
def partitioned_bundle(tmp_path_factory):
    root = tmp_path_factory.mktemp("partitioned_pipeline")
    source = root / "original_sources"
    (source / "docs").mkdir(parents=True)
    (source / "docs/NOTICE.txt").write_text(
        "Original synthetic integration fixtures, dedicated under CC0-1.0.\n",
        encoding="utf-8",
    )
    rows = []
    for key, marker in (("ambre", "Ambrelune"), ("azur", "Azurive"), ("cedre", "Cèdreclair")):
        texts = {
            "body": (
                f"À {marker}, les habitants réparent le pont près du jardin. "
                "La réunion débute tôt et chacun apporte ses outils. "
                "Une nouvelle salle accueille les jeunes lecteurs du village.\n\n"
                f"Le conseil de {marker} prépare une fête locale. "
                "Les voisins offrent des fleurs et partagent un repas paisible.\n"
            ),
            "title": f"La chronique de {marker}\nÉchos de {marker}\n",
            "advertisement": (
                f"Atelier de {marker} : meubles solides et réparation soignée. "
                "Le magasin ouvre chaque matin, près de la place du village.\n"
            ),
        }
        for role, text in texts.items():
            relative = f"docs/{key}-{role}.txt"
            (source / relative).write_text(text, encoding="utf-8")
            rows.append({
                "path": relative,
                "role": role,
                "source_document_id": f"original-{key}-{role}",
                "source_group_id": f"original-group-{key}",
                "language": "fr",
                "date": "2026-10-07",
                "source_uri": f"urn:mille-feuilles:integration:{key}:{role}",
                "content_type": "original_synthetic_demonstration",
                "historical_corpus": False,
                "rights": {
                    "status": "verified", "license": "CC0-1.0",
                    "evidence_path": "docs/NOTICE.txt",
                    "attribution": "Mille Feuilles integration fixtures",
                    "redistribution_allowed": True,
                },
            })
    manifest = source / "import.jsonl"
    manifest.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    source_before = snapshot(source)
    bundle = root / "bundle"
    imported = import_texts(manifest, bundle)
    assert imported["status"] == "pass", imported
    assert validate_catalog(bundle) == []
    plan = assign_partitions(bundle, {"train": 80, "dev": 10, "test": 10}, seed=917)
    assert snapshot(source) == source_before
    assert size_bytes(root) < 20_000_000
    return {
        "root": root, "source": source, "source_before": source_before,
        "bundle": bundle, "catalog": load_catalog(bundle), "plan": plan,
        "rows": rows, "import_report": imported,
    }


@pytest.fixture(scope="module")
def train_lot(partitioned_bundle):
    fixture = partitioned_bundle
    root, bundle = fixture["root"], fixture["bundle"]
    source_before, bundle_before = snapshot(fixture["source"]), snapshot(bundle)
    output, replay = root / "train_lot", root / "train_replay"
    config = Config(
        width=800, height=1100, columns=4, degradation="clean", seed=319, partition="train"
    )
    environment = pipeline.environment()
    git_state = pipeline.git_state()
    with pytest.MonkeyPatch.context() as patch:
        # Concurrent development must not masquerade as nondeterministic output.
        patch.setattr(pipeline, "environment", lambda: deepcopy(environment))
        patch.setattr(pipeline, "git_state", lambda: git_state)
        usage = pipeline.shutil.disk_usage(root)
        if usage.free < 600_000_000:
            # Real footprint is asserted < 20 MB. Production keeps its guard;
            # this bounded fixture should not depend on a host's 500 MB reserve.
            assert usage.free > 40_000_000, "Insufficient space even for the bounded fixture"
            patch.setattr(
                pipeline.shutil, "disk_usage",
                lambda _: type(usage)(usage.total, usage.total - 1_000_000_000, 1_000_000_000),
            )
        report = pipeline.build_dataset(output, config, count=1, jobs=1, asset_source=bundle)
        assert report["status"] == "pass", report["errors"]
        # Replay consumes only the train lot and must not need dev/test bytes.
        replay_report = pipeline.build_dataset(replay, config, count=1, jobs=1, asset_source=output)
        assert replay_report["status"] == "pass", replay_report["errors"]
    assert snapshot(fixture["source"]) == source_before
    assert snapshot(bundle) == bundle_before
    assert size_bytes(root) < 20_000_000
    return {**fixture, "output": output, "replay": replay, "config": config}


def test_import_keeps_original_bytes_and_does_not_claim_external_test_protection(partitioned_bundle):
    fixture = partitioned_bundle
    report = fixture["import_report"]
    assert len(report["accepted"]) == 9
    assert report["rejected"] == []
    assert report["external_protection"] == "NOT EVALUATED"
    assert all(item["status"] == "not_evaluated" for item in report["exclusions"].values())
    rows = {row["source_document_id"]: row for row in fixture["rows"]}
    for asset in fixture["catalog"]["assets"]:
        if asset["kind"] != "text":
            continue
        row = rows[asset["metadata"]["source_document_id"]]
        expected = (fixture["source"] / row["path"]).read_bytes()
        assert (fixture["bundle"] / asset["path"]).read_bytes() == expected
        assert asset["metadata"]["source_group_id"] == row["source_group_id"]
        assert asset["metadata"]["historical_corpus"] is False
        assert asset["metadata"]["content_type"] == "original_synthetic_demonstration"
    assert snapshot(fixture["source"]) == fixture["source_before"]


def test_components_and_observed_character_counts_are_not_falsely_reported_as_ratios(partitioned_bundle):
    fixture = partitioned_bundle
    plan = fixture["plan"]
    assets = {a["id"]: a for a in fixture["catalog"]["assets"] if a["kind"] == "text"}
    assert len(plan["components"]) == 3
    assignments = {}
    observed = {}
    for partition in ("train", "dev", "test"):
        selected = load_partition(fixture["bundle"], partition)
        assert selected == set(plan["partitions"][partition])
        assert Counter(assets[aid]["metadata"]["role"] for aid in selected) == {
            "body": 1, "title": 1, "advertisement": 1,
        }
        groups = {assets[aid]["metadata"]["source_group_id"] for aid in selected}
        assert len(groups) == 1
        assignments[partition] = groups
        observed[partition] = sum(
            len((fixture["bundle"] / assets[aid]["path"]).read_text(encoding="utf-8"))
            for aid in selected
        )
    assert len(set.union(*assignments.values())) == 3
    assert plan["characters"] == observed
    assert plan["ratios"] == {"train": 80, "dev": 10, "test": 10}
    # Three indivisible groups cannot realize 80/10/10. The recorded targets
    # remain requests; recorded character counts must report what happened.
    assert observed["train"] / sum(observed.values()) != pytest.approx(0.8, abs=0.1)


def test_a_planned_bundle_requires_an_explicit_partition_before_any_write(partitioned_bundle):
    fixture = partitioned_bundle
    bundle = fixture["bundle"]
    before = snapshot(bundle)
    destination = fixture["root"] / "forbidden_mixed_partitions"
    assert not destination.exists()
    with pytest.raises(ValueError, match="(?i)partition"):
        pipeline.build_dataset(
            destination,
            Config(width=800, height=1100, columns=4),
            count=1, jobs=1, asset_source=bundle,
        )
    assert not destination.exists(), "Partition selection must be checked before creating output"
    assert snapshot(bundle) == before
    assert snapshot(fixture["source"]) == fixture["source_before"]


def test_only_train_text_assets_and_bytes_are_copied(train_lot):
    fixture = train_lot
    allowed = set(fixture["plan"]["partitions"]["train"])
    originals = {a["id"]: a for a in fixture["catalog"]["assets"] if a["kind"] == "text"}
    for root in (fixture["output"], fixture["replay"]):
        registry = load_json(root / "assets.json")
        texts = {a["id"]: a for a in registry["assets"] if a["kind"] == "text"}
        assert set(texts) == allowed
        retained_catalog = load_catalog(root)
        assert {a["id"] for a in retained_catalog["assets"] if a["kind"] == "text"} == allowed
        for aid, asset in originals.items():
            if aid in allowed:
                assert (root / asset["path"]).read_bytes() == (fixture["bundle"] / asset["path"]).read_bytes()
            else:
                assert not (root / asset["path"]).exists(), "Excluded source must not be copied"
        excluded_bytes = [
            (fixture["bundle"] / a["path"]).read_bytes().strip()
            for aid, a in originals.items() if aid not in allowed
        ]
        for path in root.rglob("*"):
            if path.is_file():
                value = path.read_bytes()
                assert all(secret not in value for secret in excluded_bytes), path


def test_train_page_provenance_and_article_links_stay_with_selected_sources(train_lot):
    fixture = train_lot
    root = fixture["output"]
    allowed = set(fixture["plan"]["partitions"]["train"])
    registry = load_json(root / "assets.json")
    assets = {a["id"]: a for a in registry["assets"]}
    manifest = load_json(root / "manifest.json")
    assert len(manifest["pages"]) == 1
    record = manifest["pages"][0]
    page = load_json(root / record["path"])
    assert validate_page(page) == []
    assert page["provenance"]["parameters"]["partition"] == "train"
    assert set(page["provenance"]["asset_ids"]) & {
        a["id"] for a in fixture["catalog"]["assets"] if a["kind"] == "text"
    } <= allowed
    article_texts = composed_articles(page)
    assert page["provenance"]["text_spans"]
    used_groups = set()
    articles = {article["id"]: article for article in page["articles"]}
    blocks = {block["id"]: block for block in page["blocks"]}
    for span in page["provenance"]["text_spans"]:
        assert span["asset_id"] in allowed
        asset = assets[span["asset_id"]]
        metadata = asset["metadata"]
        assert span["source_document_id"] == metadata["source_document_id"]
        used_groups.add(metadata["source_group_id"])
        article = articles[span["article_id"]]
        assert span["block_ids"]
        assert all(blocks[bid]["article_id"] == article["id"] for bid in span["block_ids"])
        positions = [article["block_ids"].index(bid) for bid in span["block_ids"]]
        assert positions == sorted(set(positions)), "Span blocks follow their declared article"
        raw = (root / asset["path"]).read_text(encoding="utf-8")
        expected = normalized(raw[span["start"]:span["end"]])
        bound_article = deepcopy(article)
        bound_article["block_ids"] = span["block_ids"]
        bound_text = composed_articles({**page, "articles": [bound_article]})[0]
        assert expected and expected == normalized(bound_text)
        assert any(expected in actual for actual in article_texts)
    assert used_groups == set(record["source_group_ids"])
    assert len(used_groups) == 1
    assert validate_dataset(root)["status"] == "pass"


def test_train_replay_from_filtered_lot_is_bit_identical(train_lot):
    fixture = train_lot
    comparison = pipeline.compare_lots(fixture["output"], fixture["replay"])
    assert comparison["status"] == "pass", comparison
    assert comparison["files_compared"] > 15


def test_partition_receipt_and_original_metadata_are_pinned_by_the_manifest(train_lot):
    fixture = train_lot
    for root in (fixture["output"], fixture["replay"]):
        config = load_json(root / "config.json")
        manifest = load_json(root / "manifest.json")
        receipt = config["partition"]
        assert config["render"]["partition"] == "train"
        assert manifest["extensions"]["mf:partition"] == receipt
        assert receipt == {
            "version": "1", "name": "train", "path": "provenance/partition.json",
            "sha256": sha256(fixture["bundle"] / "assets/partition.json"),
            "source_catalog_path": "provenance/source-catalog.json",
            "source_catalog_sha256": sha256(fixture["bundle"] / "assets/catalog.json"),
        }
        assert (root / receipt["path"]).read_bytes() == (fixture["bundle"] / "assets/partition.json").read_bytes()
        assert (root / receipt["source_catalog_path"]).read_bytes() == (fixture["bundle"] / "assets/catalog.json").read_bytes()
        inventory = {item["path"]: item["sha256"] for item in manifest["artifacts"]}
        for relative in ("config.json", receipt["path"], receipt["source_catalog_path"]):
            assert inventory[relative] == sha256(root / relative)
        assert manifest["config"]["sha256"] == sha256(root / "config.json")


def test_import_report_is_preserved_and_pinned_in_train_and_replay(train_lot):
    fixture = train_lot
    original = fixture["bundle"] / "assets/import-report.json"
    expected = original.read_bytes()
    expected_hash = sha256(original)
    for root in (fixture["output"], fixture["replay"]):
        manifest = load_json(root / "manifest.json")
        reference = manifest["extensions"]["mf:import_report"]
        assert reference == {
            "path": "provenance/import-report.json", "sha256": expected_hash,
        }
        carried = root / reference["path"]
        assert carried.read_bytes() == expected
        assert sha256(carried) == reference["sha256"]
        inventory = {item["path"]: item["sha256"] for item in manifest["artifacts"]}
        assert inventory[reference["path"]] == expected_hash
        assert load_json(carried)["external_protection"] == "NOT EVALUATED"


def test_a_filtered_train_lot_cannot_generate_dev(train_lot):
    fixture = train_lot
    root = fixture["output"]
    before = snapshot(root)
    destination = fixture["root"] / "forbidden_dev"
    with pytest.raises(ValueError, match="(?i)partition"):
        pipeline.build_dataset(
            destination,
            Config(width=800, height=1100, columns=4, partition="dev"),
            count=1, jobs=1, asset_source=root,
        )
    assert snapshot(root) == before
    assert not (destination / "manifest.json").exists()
    assert not list(destination.glob("images/*.png"))


def test_rehashed_partition_mismatch_cannot_be_accepted_as_train(train_lot):
    fixture = train_lot
    broken = fixture["root"] / "tampered_selection"
    shutil.copytree(fixture["output"], broken)
    manifest = load_json(broken / "manifest.json")
    config = load_json(broken / "config.json")
    receipt = config["partition"]
    plan_path = broken / receipt["path"]
    plan = load_json(plan_path)
    # Every digest is refreshed: only semantic selection checks can detect
    # that the copied train assets no longer match the claimed train list.
    plan["partitions"]["train"], plan["partitions"]["dev"] = (
        plan["partitions"]["dev"], plan["partitions"]["train"]
    )
    write_json(plan_path, plan)
    receipt["sha256"] = sha256(plan_path)
    manifest["extensions"]["mf:partition"] = deepcopy(receipt)
    write_json(broken / "config.json", config)
    manifest["config"]["sha256"] = sha256(broken / "config.json")
    for item in manifest["artifacts"]:
        if item["path"] in ("config.json", receipt["path"]):
            item["sha256"] = sha256(broken / item["path"])
    write_json(broken / "manifest.json", manifest)
    result = validate_dataset(broken)
    checks = {check["name"]: check["status"] for check in result["checks"]}
    assert checks["file_hashes"] == "pass", result["errors"]
    assert result["status"] == "fail"
    assert any("partition" in error.lower() for error in result["errors"])
    assert size_bytes(fixture["root"]) < 20_000_000


def test_rehashed_train_character_counts_must_match_copied_text(train_lot):
    fixture = train_lot
    broken = fixture["root"] / "tampered_train_characters"
    shutil.copytree(fixture["output"], broken)
    manifest = load_json(broken / "manifest.json")
    config = load_json(broken / "config.json")
    receipt = config["partition"]
    plan_path = broken / receipt["path"]
    plan = load_json(plan_path)
    selected_components = [c for c in plan["components"] if c["partition"] == "train"]
    assert len(selected_components) == 1
    # The plan remains internally consistent and all files retain valid hashes.
    # Only reading the copied train texts exposes the invented character count.
    selected_components[0]["chars"] += 1_000_000
    plan["characters"]["train"] += 1_000_000
    write_json(plan_path, plan)
    receipt["sha256"] = sha256(plan_path)
    manifest["extensions"]["mf:partition"] = deepcopy(receipt)
    write_json(broken / "config.json", config)
    manifest["config"]["sha256"] = sha256(broken / "config.json")
    for item in manifest["artifacts"]:
        if item["path"] in ("config.json", receipt["path"]):
            item["sha256"] = sha256(broken / item["path"])
    write_json(broken / "manifest.json", manifest)

    # Exports are unchanged; disable their prerequisite-failure cascade so
    # this rejection must come exclusively from the character-count check.
    result = validate_dataset(broken, verify_exports=False)
    checks = {check["name"]: check["status"] for check in result["checks"]}
    assert checks["file_hashes"] == "pass", result["errors"]
    assert checks["partition_receipt"] == "pass", result["errors"]
    assert {name for name, status in checks.items() if status == "fail"} == {"partition_characters"}
    assert result["status"] == "fail", "Invented train character counts were accepted"
    assert result["errors"]
    assert all(
        "partition" in error.lower() and "character" in error.lower()
        for error in result["errors"]
    ), result["errors"]
    assert size_bytes(fixture["root"]) < 20_000_000
