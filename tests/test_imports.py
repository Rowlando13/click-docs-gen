import click_docs_gen


def test_placeholder() -> None:
    assert click_docs_gen.placeholder() is True
