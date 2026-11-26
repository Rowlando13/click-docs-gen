# Copied directly from click-extra. For click internal use only.
"""The ``click:source`` and ``click:run`` directives.

Based on `Pallets' Sphinx Themes
<https://github.com/pallets/pallets-sphinx-themes>`_, released under a
BSD-3-Clause license, by way of click-extra. Compared to the former, it
supports MyST syntax, ``code-block`` options, show/hide toggles, and reports
the document location of a failing block.
"""

from __future__ import annotations

import typing as t
from functools import cached_property

from docutils.parsers.rst import directives
from sphinx.directives.code import CodeBlock

from ._base import ContentOffsetMixin
from ._base import make_cleanup
from ._base import parse_into_section
from ._base import StatelessDomain
from .click_runner import ClickRunner

if t.TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Iterable

    from docutils import nodes
    from sphinx.application import Sphinx
    from sphinx.util.typing import OptionSpec

RST_INDENT = " " * 3
"""The indentation used for rST code block lines."""


def _code_fence(lines: Iterable[str]) -> str:
    """Return a backtick fence longer than any backtick run opening ``lines``.

    The fence is never shorter than three backticks.
    """
    longest = max(
        (len(line) - len(line.lstrip("`")) for line in map(str.lstrip, lines)),
        default=0,
    )
    return "`" * max(3, longest + 1)


class ClickDirective(ContentOffsetMixin):
    """Base class of the ``click:*`` directives."""

    has_content = True

    required_arguments = 0
    optional_arguments = 1
    """The optional argument overrides the default Pygments language."""

    final_argument_whitespace = False

    option_spec: t.ClassVar[OptionSpec] = CodeBlock.option_spec | {
        "language": directives.unchanged_required,
        "show-source": directives.flag,
        "hide-source": directives.flag,
        "show-results": directives.flag,
        "hide-results": directives.flag,
        "show-prompt": directives.flag,
        "hide-prompt": directives.flag,
        "emphasize-result-lines": CodeBlock.option_spec["emphasize-lines"],
    }
    """Options supported by this directive.

    The same options as :class:`sphinx.directives.code.CodeBlock`, plus some
    specific to Click directives. ``emphasize-lines`` applies to the source
    block, ``emphasize-result-lines`` to the results block.
    """

    default_language: t.ClassVar[str]
    """Default Pygments language of the rendered code block."""

    source_language: t.ClassVar[str | None] = None
    """Language of the source block, when it differs from :attr:`language`."""

    show_source_by_default: t.ClassVar[bool] = True
    show_results_by_default: t.ClassVar[bool] = True
    show_prompt_by_default: t.ClassVar[bool] = True

    runner_method: t.ClassVar[str]
    """Name of the :class:`ClickRunner` method executing the block."""

    runner_attr: t.ClassVar[str] = "click_docs_gen_runner"
    """Name of the doctree attribute holding the per-document runner."""

    @property
    def runner(self) -> ClickRunner:
        """Get or create the per-document runner."""
        runner = getattr(self.state.document, self.runner_attr, None)
        if runner is None:
            runner = ClickRunner()
            setattr(self.state.document, self.runner_attr, runner)
        return t.cast(ClickRunner, runner)

    @cached_property
    def language(self) -> str:
        """Pygments lexer for the code block: ``:language:`` option, then the
        directive argument, then :attr:`default_language`.
        """
        if "language" in self.options:
            return str(self.options["language"])
        if self.arguments:
            return str(self.arguments[0])
        return self.default_language

    def code_block_options(self, target: str = "source") -> list[str]:
        """Render the options supported by Sphinx' ``code-block`` directive.

        ``target`` is ``"source"`` or ``"results"``, routing
        ``emphasize-lines`` and ``emphasize-result-lines`` to the right block.
        """
        options = []
        for option_id in CodeBlock.option_spec:
            if option_id == "emphasize-lines":
                if target == "source" and "emphasize-lines" in self.options:
                    options.append(f":emphasize-lines: {self.options[option_id]}")
                elif target == "results" and "emphasize-result-lines" in self.options:
                    options.append(
                        f":emphasize-lines: {self.options['emphasize-result-lines']}"
                    )
                continue
            if option_id in self.options:
                value = self.options[option_id]
                line = f":{option_id}:"
                if value:
                    line += f" {value}"
                options.append(line)
        return options

    def _toggle(self, subject: str, default: bool) -> bool:
        """Resolve a ``show-<subject>`` / ``hide-<subject>`` option pair.

        The last one given wins. With neither, ``default`` answers.
        """
        value = default
        for option_id in self.options:
            if option_id == f"show-{subject}":
                value = True
            elif option_id == f"hide-{subject}":
                value = False
        return value

    @cached_property
    def show_source(self) -> bool:
        """Whether to render the source code of the block."""
        return self._toggle("source", self.show_source_by_default)

    @cached_property
    def show_results(self) -> bool:
        """Whether to render the results of running the block."""
        return self._toggle("results", self.show_results_by_default)

    @cached_property
    def show_prompt(self) -> bool:
        """Whether to draw the invocation above the output it produced."""
        return self._toggle("prompt", self.show_prompt_by_default)

    def render_code_block(
        self,
        lines: Iterable[str],
        language: str,
        target: str = "source",
    ) -> list[str]:
        """Render a ``code-block`` holding ``lines``, in MyST or rST syntax."""
        block: list[str] = []
        lines = list(lines)
        if not lines:
            return block

        fence = _code_fence(lines)
        code_directive = (
            f"{fence}{{code-block}}" if self.is_myst_syntax else ".. code-block::"
        )
        block.append(f"{code_directive} {language}")

        indent = "" if self.is_myst_syntax else RST_INDENT
        block.extend(indent + line for line in self.code_block_options(target))

        # A blank line keeps the first body line from reading as an option.
        block.append("")

        block.extend(indent + line for line in lines)

        if self.is_myst_syntax:
            block.append(fence)

        return block

    def run(self) -> list[nodes.Node]:
        """Execute the directive and render its source and results."""
        runner_func = getattr(self.runner, self.runner_method)
        results: list[str] = runner_func(self)

        if not self.show_source and not self.show_results:
            return []

        lines = []
        if self.show_source:
            language = self.source_language or self.language
            lines.extend(self.render_code_block(self.content, language, "source"))
        if self.show_results:
            lines.extend(self.render_code_block(results, self.language, "results"))

        return parse_into_section(self, lines)


class SourceDirective(ClickDirective):
    """Declare a Click CLI and render its source code as Python."""

    default_language = "python"
    show_source_by_default = True
    show_results_by_default = False
    runner_method = "execute_source"


class RunDirective(ClickDirective):
    """Run a Click CLI and render the results as a shell session."""

    default_language = "shell-session"
    show_source_by_default = False
    show_results_by_default = True
    runner_method = "run_cli"
    source_language: t.ClassVar[str | None] = SourceDirective.default_language


class ClickDomain(StatelessDomain):
    """Register ``click:source`` (alias ``click:example``) and ``click:run``."""

    name = "click"
    label = "Click"
    directives: t.ClassVar[dict[str, type[t.Any]]] = {
        "source": SourceDirective,
        "example": SourceDirective,
        "run": RunDirective,
    }


cleanup_runner: Callable[[Sphinx, nodes.document], None] = make_cleanup(
    ClickDirective.runner_attr
)
"""Drop the :class:`ClickRunner` from the doctree once the document is read."""
