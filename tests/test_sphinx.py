from __future__ import annotations

import textwrap
import typing as t

import pytest
from sphinx.errors import SphinxError
from sphinx.testing.util import SphinxTestApp

if t.TYPE_CHECKING:
    from pathlib import Path

CLI_SOURCE = """\
from click import command, echo, option

@command
@option("--name", default="World", help="The person to greet.")
def hello(name):
    \"\"\"Greet someone.\"\"\"
    echo(f"Hello, {name}!")
"""

RST_DOC = f"""\
Title
=====

.. click:source::

{textwrap.indent(CLI_SOURCE, "   ")}
.. click:run::

   result = invoke(hello, args=["--name", "Alice"])
   assert result.exit_code == 0
   assert result.output == "Hello, Alice!\\n"
"""

MYST_DOC = f"""\
# Title

```{{click:source}}
{CLI_SOURCE}```

```{{click:run}}
:show-source:
result = invoke(hello, args=["--help"])
assert result.exit_code == 0
assert "Greet someone." in result.stdout
```
"""


def build(tmp_path: Path, filename: str, content: str, enable: bool = True) -> str:
    """Build ``content`` as the root document and return its text output."""
    srcdir = tmp_path / "src"
    srcdir.mkdir()
    extensions = ["click_docs_gen.sphinx"]
    if filename.endswith(".md"):
        extensions.append("myst_parser")
    (srcdir / "conf.py").write_text(
        f"extensions = {extensions!r}\n"
        f"click_docs_gen_enable_exec_directives = {enable!r}\n"
        "source_suffix = {'.rst': 'restructuredtext', '.md': 'markdown'}\n"
    )
    (srcdir / filename).write_text(content)
    app = SphinxTestApp("text", srcdir=srcdir, builddir=tmp_path / "build")
    try:
        app.build()
        out = (app.outdir / "index.txt").read_text()
        out += app.warning.getvalue()
    finally:
        app.cleanup()
    return out


def test_rst(tmp_path: Path) -> None:
    out = build(tmp_path, "index.rst", RST_DOC)
    assert "def hello(name):" in out
    assert "$ hello --name Alice\n   Hello, Alice!" in out
    assert "result = invoke" not in out


def test_example_alias(tmp_path: Path) -> None:
    out = build(tmp_path, "index.rst", RST_DOC.replace("click:source", "click:example"))
    assert "def hello(name):" in out
    assert "$ hello --name Alice\n   Hello, Alice!" in out


def test_myst(tmp_path: Path) -> None:
    out = build(tmp_path, "index.md", MYST_DOC)
    assert "def hello(name):" in out
    assert "result = invoke(hello" in out
    assert "$ hello --help" in out
    assert "Greet someone." in out


def test_hide_source_and_prompt(tmp_path: Path) -> None:
    doc = RST_DOC.replace(
        ".. click:source::\n", ".. click:source::\n   :hide-source:\n"
    ).replace(".. click:run::\n", ".. click:run::\n   :hide-prompt:\n")
    out = build(tmp_path, "index.rst", doc)
    assert "def hello" not in out
    assert "$ hello" not in out
    assert "Hello, Alice!" in out


def test_input_and_env(tmp_path: Path) -> None:
    doc = """\
Title
=====

.. click:source::

   import click

   @click.command
   @click.option("--name", prompt=True, envvar="GREETING")
   def hi(name):
       click.echo(f"Hi {name}")

   @click.command
   @click.argument("f", type=click.File())
   def cat(f):
       click.echo(f.read().upper(), nl=False)

.. click:run::

   result = invoke(hi, input=["Bob"])
   assert result.output.endswith("Hi Bob\\n")
   invoke(hi, env={"GREETING": "Eve"})
   invoke(cat, args=["-"], input=["a", "b"], terminate_input=True)
"""
    out = build(tmp_path, "index.rst", doc)
    assert "$ hi\n   Name: Bob\n   Hi Bob" in out
    assert "$ GREETING=Eve hi\n   Hi Eve" in out
    assert "$ cat -\n   a\n   b\n   ^D\n   A\n   B" in out


def test_failed_assertion_aborts_build(tmp_path: Path) -> None:
    doc = RST_DOC.replace('"Hello, Alice!\\n"', '"Wrong"')
    with pytest.raises((AssertionError, SphinxError)):
        build(tmp_path, "index.rst", doc)


def test_reserved_name_conflict(tmp_path: Path) -> None:
    doc = RST_DOC.replace(
        "   result = invoke(", "   invoke = None\n   result = invoke("
    )
    with pytest.raises(RuntimeError, match="Local variable 'invoke'"):
        build(tmp_path, "index.rst", doc)


def test_disabled_by_default(tmp_path: Path) -> None:
    out = build(tmp_path, "index.rst", RST_DOC, enable=False)
    assert "$ hello" not in out
    assert 'Unknown directive type "click:run"' in out
