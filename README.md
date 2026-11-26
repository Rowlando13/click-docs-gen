# click-docs-gen

Utilities for automatically documenting [Click] applications.

!!For click internal use only!!

[Click]: https://click.palletsprojects.com/

## Sphinx directives

`click_docs_gen.sphinx` adds two directives, adapted from [click-extra]:
`click:source` (alias `click:example`) defines and shows a Click CLI, and
`click:run` runs it at build time and shows the output as a terminal session.

```python
# conf.py
extensions = ["click_docs_gen.sphinx"]
click_docs_gen_enable_exec_directives = True
```

```rst
.. click:source::

   import click

   @click.command
   @click.option("--name", default="World")
   def hello(name):
       click.echo(f"Hello, {name}!")

.. click:run::

   result = invoke(hello, args=["--name", "Alice"])
   assert result.output == "Hello, Alice!\n"
```

Both directives run arbitrary Python with the privileges of the Sphinx
build, so they stay disabled until `conf.py` opts in. A failing assertion
aborts the build. Options: `:show-source:`/`:hide-source:`,
`:show-results:`/`:hide-results:`, `:show-prompt:`/`:hide-prompt:`,
`:language:`, `:emphasize-result-lines:`, and every `code-block` option.

[click-extra]: https://github.com/kdeldycke/click-extra

## Development

This project uses [uv] and the same tooling as [pallets/click].

```
uv sync
uv run pre-commit install --install-hooks
uv run tox run          # tests, style, typing
uv run tox run -e typing
```

This project is not published to PyPI.

[uv]: https://docs.astral.sh/uv/
[pallets/click]: https://github.com/pallets/click
