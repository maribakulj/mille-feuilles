"""Declared text spans must be found in the composed articles they claim to feed.

Contract under test (validate_text_provenance(page, text_assets) -> list[str]):
each span, sliced from the raw asset text, NFC-normalized and split on
whitespace, appears as a contiguous word sequence inside one article. Articles
are rebuilt from block_ids -> line_ids -> word_ids, joining hyphenation groups
through reconstructed_text. Spans carry no article_id and need not follow the
reading order; the masthead template has no span; repeated segments are not
attributed uniquely; coverage of every composed word is not claimed.
"""

import json
import shutil
import unicodedata
from pathlib import Path

import pytest

from mille_feuilles.render import Config, render_page
from mille_feuilles.validation import validate_page, validate_text_provenance

ROOT = Path(__file__).resolve().parents[1]

BODY = (
    "La séance  fut levée\nà minuit, sans débat.\n\n"
    "Le soir tombe vite sur la dissolution rapide du conseil.\n\n"
    "Il viendra peut-être demain — Paris, le 3 mai : rien."
)
TITLE = "Nouvelles du jour\nChronique locale\n"
TEXTS = {"body": BODY, "title": TITLE}


def span(asset_id, segment, texts=TEXTS):
    source = texts[asset_id]
    start = source.index(segment)
    return {
        "asset_id": asset_id,
        "start": start,
        "end": start + len(segment),
        "source_document_id": f"doc_{asset_id}",
    }


def hyp(group, part, whole):
    return {"group_id": group, "part": part, "reconstructed_text": whole}


def make_page(articles, spans, loose=()):
    """articles: list of articles; article = list of blocks; block = list of
    lines; line = list of tokens, a token being a str or (text, hyphenation).
    loose: textual blocks outside any article, each composed separately."""
    page = {
        "page_id": "t",
        "articles": [],
        "blocks": [],
        "lines": [],
        "words": [],
        "provenance": {"text_spans": spans},
    }
    owners = [({"id": f"a{a}", "block_ids": []}, blocks) for a, blocks in enumerate(articles)]
    owners += [(None, [block_lines]) for block_lines in loose]
    for article, blocks in owners:
        if article:
            page["articles"].append(article)
        for block_lines in blocks:
            block = {
                "id": f"b{len(page['blocks'])}",
                "category": "texte",
                "article_id": article["id"] if article else None,
                "line_ids": [],
            }
            if article:
                article["block_ids"].append(block["id"])
            page["blocks"].append(block)
            for tokens in block_lines:
                line = {"id": f"l{len(page['lines'])}", "block_id": block["id"], "word_ids": []}
                texts, cursor = [], 0
                for token in tokens:
                    text, hyphenation = token if isinstance(token, tuple) else (token, None)
                    word = {
                        "id": f"w{len(page['words'])}",
                        "line_id": line["id"],
                        "text": text,
                        "char_span": [cursor, cursor + len(text)],
                        "hyphenation": hyphenation,
                    }
                    cursor += len(text) + 1
                    texts.append(text)
                    line["word_ids"].append(word["id"])
                    page["words"].append(word)
                line["text"] = " ".join(texts)
                block["line_ids"].append(line["id"])
                page["lines"].append(line)
    # A separator outside any article, as in generated pages.
    page["blocks"].append(
        {"id": f"b{len(page['blocks'])}", "category": "separateur", "article_id": None, "line_ids": []}
    )
    return page


MASTHEAD = [[["MILLE", "FEUILLES"]], [["Journal", "de", "démonstration"]]]
FIRST = "La séance  fut levée\nà minuit, sans débat."
FIRST_LINES = [["La", "séance", "fut", "levée"], ["à", "minuit,", "sans", "débat."]]


def errors(page, texts=TEXTS):
    result = validate_text_provenance(page, dict(texts))
    assert isinstance(result, list) and all(isinstance(e, str) for e in result)
    return result


def test_matching_page_with_masthead_template_and_separator_passes():
    page = make_page([MASTHEAD, [FIRST_LINES]], [span("body", FIRST)])
    assert errors(page) == []


def test_page_with_only_template_text_and_no_span_passes():
    assert errors(make_page([MASTHEAD], [])) == []


def test_source_whitespace_newlines_and_nfd_are_normalized_before_matching():
    nfd = unicodedata.normalize("NFD", BODY)
    assert nfd != BODY
    segment = unicodedata.normalize("NFD", FIRST)
    start = nfd.index(segment)
    declared = {"asset_id": "body", "start": start, "end": start + len(segment),
                "source_document_id": "doc_body"}
    page = make_page([[FIRST_LINES]], [declared])
    assert errors(page, {"body": nfd, "title": TITLE}) == []


def test_span_pointing_to_another_paragraph_is_rejected():
    page = make_page([[FIRST_LINES]], [span("body", "Il viendra peut-être demain")])
    assert errors(page)


def test_span_with_offsets_of_the_wrong_asset_is_rejected():
    declared = span("body", FIRST)
    declared["asset_id"] = "title"
    assert errors(make_page([[FIRST_LINES]], [declared]))


def test_unknown_asset_is_reported_without_exception():
    declared = span("body", FIRST)
    declared["asset_id"] = "missing"
    assert errors(make_page([[FIRST_LINES]], [declared]))


@pytest.mark.parametrize(
    "lines",
    [
        [["La", "séance", "fut", "levée"], ["à", "minuit,", "sans", "debat."]],  # accent lost
        [["La", "séance", "fut", "levée"], ["à", "minuit;", "sans", "débat."]],  # punctuation
        [["La", "fut", "séance", "levée"], ["à", "minuit,", "sans", "débat."]],  # order
        [["La", "séance", "fut", "levée"], ["à", "minuit,", "et", "sans", "débat."]],  # insertion
        [["La", "séance", "levée"], ["à", "minuit,", "sans", "débat."]],  # deletion
    ],
)
def test_mutated_composed_content_is_rejected(lines):
    assert errors(make_page([[lines]], [span("body", FIRST)]))


def test_title_and_body_spans_declared_in_reverse_reading_order_pass():
    body = "Le soir tombe vite"
    article = [[["Chronique", "locale"]], [["Le", "soir", "tombe", "vite"]]]
    page = make_page([article], [span("body", body), span("title", "Chronique locale")])
    assert errors(page) == []


def test_hyphenation_across_blocks_is_joined_with_reconstructed_text():
    whole = "dissolution"
    article = [
        [["sur", "la", ("disso-", hyp("h0", "start", whole))]],
        [[("lution", hyp("h0", "end", whole)), "rapide"]],
    ]
    page = make_page([article], [span("body", "sur la dissolution rapide")])
    assert errors(page) == []


def test_lexical_hyphen_and_dash_are_kept_as_composed():
    segment = "Il viendra peut-être demain — Paris, le 3 mai : rien."
    lines = [["Il", "viendra", "peut-être", "demain", "—"], ["Paris,", "le", "3", "mai", ":", "rien."]]
    assert errors(make_page([[lines]], [span("body", segment)])) == []


def test_suspended_lexical_hyphen_at_line_end_is_not_stripped():
    # "pré-" ends a line but belongs to no hyphenation group: it is source text.
    texts = dict(TEXTS, body="les scrutins pré- et post-électoraux")
    lines = [["les", "scrutins", "pré-"], ["et", "post-électoraux"]]
    declared = span("body", "les scrutins pré- et post-électoraux", texts)
    assert errors(make_page([[lines]], [declared]), texts) == []


def test_line_break_at_a_lexical_hyphen_without_group_is_not_silently_joined():
    lines = [["Il", "viendra", "peut-"], ["être", "demain"]]
    assert errors(make_page([[lines]], [span("body", "Il viendra peut-être demain")]))


def test_visible_hyphen_of_a_group_is_not_kept_as_lexical_text():
    # Without the group, "disso-" + "lution" must not match "disso-lution" either.
    lines = [["la", "disso-"], ["lution", "rapide"]]
    texts = dict(TEXTS, body="la disso-lution rapide")
    assert errors(make_page([[lines]], [span("body", "la disso-lution rapide", texts)]), texts)


def test_repeated_segment_in_two_articles_passes_without_unique_attribution():
    article = [[["Le", "soir", "tombe", "vite"]]]
    spans = [span("body", "Le soir tombe vite"), span("body", "Le soir tombe vite")]
    assert errors(make_page([article, article], spans)) == []


def test_segment_cannot_be_assembled_across_two_articles():
    first = [[["Le", "soir"]]]
    second = [[["tombe", "vite"]]]
    page = make_page([first, second], [span("body", "Le soir tombe vite")])
    assert errors(page)


def test_textual_block_without_article_is_its_own_stream():
    loose = [["Le", "soir", "tombe", "vite"]]
    page = make_page([[FIRST_LINES]], [span("body", FIRST), span("body", "Le soir tombe vite")],
                     loose=[loose])
    assert errors(page) == []
    mutated = make_page([[FIRST_LINES]], [span("body", "Le soir tombe vite")],
                        loose=[[["Le", "soir", "tombe", "tard"]]])
    assert errors(mutated)


def test_segment_cannot_join_an_article_and_an_unassigned_block():
    page = make_page([[[["Le", "soir"]]]], [span("body", "Le soir tombe vite")],
                     loose=[[["tombe", "vite"]]])
    assert errors(page)


def test_links_not_storage_order_define_the_article_text():
    whole = "dissolution"
    article = [
        [["sur", "la", ("disso-", hyp("h0", "start", whole))]],
        [[("lution", hyp("h0", "end", whole)), "rapide"]],
    ]
    declared = [span("body", "sur la dissolution rapide")]
    page = make_page([article], declared)
    for key in ("articles", "blocks", "lines", "words"):
        page[key].reverse()
    assert errors(page) == []
    wrong = make_page([article], [span("body", "la dissolution rapide du conseil")])
    for key in ("articles", "blocks", "lines", "words"):
        wrong[key].reverse()
    assert errors(wrong)


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    root = tmp_path_factory.mktemp("provenance")
    shutil.copytree(ROOT / "assets", root / "assets")
    assets = json.loads((root / "assets/catalog.json").read_text(encoding="utf-8"))["assets"]
    config = Config(width=1200, height=1656, columns=5, degradation="clean", seed=127)
    page = render_page(config, 0, assets, root)
    texts = {
        a["id"]: (root / a["path"]).read_text(encoding="utf-8") for a in assets if a["kind"] == "text"
    }
    return page, texts


def test_generated_page_passes(rendered):
    page, texts = rendered
    assert page["provenance"]["text_spans"]
    assert validate_text_provenance(page, texts) == []


def test_generated_page_with_one_mutated_body_word_fails(rendered):
    # Precondition of the helper: the mutated page stays valid for validate_page.
    page, texts = rendered
    page = json.loads(json.dumps(page))
    assert validate_page(page) == []
    header = page["articles"][0]["id"]
    blocks = {b["id"]: b for b in page["blocks"]}
    lines = {line["id"]: line for line in page["lines"]}
    target = next(
        w for w in page["words"]
        if blocks[lines[w["line_id"]]["block_id"]]["article_id"] not in (None, header)
        and w["hyphenation"] is None and w["text"].isalpha() and len(w["text"]) >= 3
    )
    # Same length and NFC; the replacement occurs in no source text.
    replacement = target["text"][:-1] + "\u1e91"
    assert unicodedata.normalize("NFC", replacement) == replacement
    assert all(replacement not in text for text in texts.values())
    line = lines[target["line_id"]]
    start, end = target["char_span"]
    assert line["text"][start:end] == target["text"]
    line["text"] = line["text"][:start] + replacement + line["text"][end:]
    target["text"] = replacement
    assert validate_page(page) == []
    assert validate_text_provenance(page, texts)
