from __future__ import annotations

from ghostcite.config import SearchConfig
from ghostcite.models import Author, Engine, ParsedFields
from ghostcite.search.planner import Strategy, plan_queries


def _fields(**kwargs: object) -> ParsedFields:
    defaults: dict[str, object] = {
        "title": "Attention is all you need",
        "authors": (Author(surname="Vaswani", given="A."),),
        "year": 2017,
    }
    return ParsedFields.model_validate({**defaults, **kwargs})


def test_article_gets_two_scholar_queries() -> None:
    queries = plan_queries(_fields(entry_type="article"))
    assert [q.strategy for q in queries] == [
        Strategy.SCHOLAR_EXACT_TITLE,
        Strategy.SCHOLAR_TITLE_AUTHOR,
    ]
    assert queries[0].params == {
        "engine": "google_scholar",
        "q": '"Attention is all you need"',
        "hl": "en",
        "num": "10",
    }
    assert queries[1].text == 'Attention is all you need author:"Vaswani"'
    assert all(q.engine is Engine.GOOGLE_SCHOLAR for q in queries)


def test_no_year_filters_are_ever_sent() -> None:
    for query in plan_queries(_fields(entry_type="book")):
        assert not {"as_ylo", "as_yhi"} & query.params.keys()


def test_books_and_theses_get_a_google_fallback() -> None:
    for entry_type in ("book", "phdthesis", "techreport"):
        queries = plan_queries(_fields(entry_type=entry_type))
        assert queries[-1].strategy is Strategy.GOOGLE_FALLBACK
        assert queries[-1].engine is Engine.GOOGLE
        assert queries[-1].params == {
            "engine": "google",
            "q": '"Attention is all you need" Vaswani',
            "hl": "en",
            "gl": "in",
        }


def test_no_title_means_no_queries() -> None:
    assert plan_queries(_fields(title=None)) == []


def test_missing_authors() -> None:
    queries = plan_queries(_fields(authors=(), entry_type="book"))
    assert queries[1].text == "Attention is all you need"
    assert queries[2].text == '"Attention is all you need"'


def test_multiword_surname_uses_last_word() -> None:
    queries = plan_queries(_fields(authors=(Author(surname="de la Fontaine"),)))
    assert queries[1].text.endswith('author:"Fontaine"')


def test_quotes_are_stripped_and_long_titles_cut_at_a_word() -> None:
    title = '\u201cQuoted\u201d "inner" ' + "word " * 80
    queries = plan_queries(_fields(title=title), SearchConfig(max_query_chars=40))
    exact = queries[0].text
    assert exact.startswith('"Quoted inner word')
    assert len(exact) <= 42  # 40 characters plus the enclosing quotes
    assert not exact[1:-1].endswith(" ")
    assert '"' not in exact[1:-1]


def test_language_and_page_size_come_from_config() -> None:
    query = plan_queries(_fields(), SearchConfig(language="hi", results_per_query=20))[0]
    assert (query.params["hl"], query.params["num"]) == ("hi", "20")


def test_scholar_requests_pin_english_and_never_bypass_serpapi_cache() -> None:
    queries = plan_queries(_fields(entry_type="book"))
    for query in queries:
        assert query.params["hl"] == "en"
        assert "no_cache" not in query.params
    assert queries[-1].params["gl"] == "in"
