# Copied directly from click-extra. For click internal use only.
"""Shared scaffolding of the ``click:*`` directives.

Holds directive-content compilation, the line-offset arithmetic of
:class:`ContentOffsetMixin`, per-document runner cleanup, and the stateless
``Domain`` boilerplate Sphinx demands of a domain that ships only directives.
"""

from __future__ import annotations

import typing as t
from functools import cached_property

from docutils import nodes
from docutils.statemachine import StringList
from sphinx.domains import Domain
from sphinx.util.docutils import SphinxDirective

if t.TYPE_CHECKING:
    from collections.abc import Callable
    from types import CodeType

    from docutils.nodes import Element
    from sphinx.addnodes import pending_xref
    from sphinx.application import Sphinx
    from sphinx.builders import Builder
    from sphinx.environment import BuildEnvironment

PLACEHOLDER_FILE = "dummy.py"
"""The ``__file__`` every directive body runs under."""


class ContentOffsetMixin(SphinxDirective):
    """Directive base reconciling the line counts of docutils and MyST.

    Both parsers expose a ``content_offset``, counted from different places, so
    anything naming a document line goes through :attr:`abs_content_offset`.
    """

    @cached_property
    def is_myst_syntax(self) -> bool:
        """Whether the directive is written with MyST syntax."""
        module: str = self.state.__module__
        return module.partition(".")[0] == "myst_parser"

    @cached_property
    def abs_content_offset(self) -> int:
        """0-based offset of the directive's first content line in the document.

        docutils counts ``content_offset`` from the top of the document,
        ``myst-parser`` from the directive's own first line.
        """
        content_offset: int = self.content_offset
        if not self.is_myst_syntax:
            return content_offset
        lineno: int = self.lineno
        return lineno + content_offset


def directive_source(directive: SphinxDirective) -> tuple[str, str]:
    """Return the ``(source_code, location)`` pair for ``directive``."""
    return "\n".join(directive.content), directive.get_location()


def compile_directive(directive: SphinxDirective) -> CodeType:
    """Compile the body of ``directive`` for later ``exec``.

    .. danger::

        The code runs with the same privileges as the Sphinx process. Only
        build documentation from trusted sources.
    """
    source_code, location = directive_source(directive)
    return compile(source_code, location, "exec")


def parse_into_section(
    directive: ContentOffsetMixin,
    lines: list[str],
) -> list[nodes.Node]:
    """Hand generated source ``lines`` back to the directive's parser.

    Each generated line is labelled with the document line the directive's
    content starts at plus its index in the block, so diagnostics point at the
    right line with either parser.
    """
    section = nodes.section()
    source_file = directive.get_source_info()[0] or ""
    offset = directive.abs_content_offset
    directive.state.nested_parse(
        StringList(
            lines,
            source_file,
            items=[(source_file, offset + index) for index in range(len(lines))],
        ),
        offset - directive.lineno if directive.is_myst_syntax else offset,
        section,
    )
    return list(section.children)


def make_cleanup(attr: str) -> Callable[[Sphinx, nodes.document], None]:
    """Build a ``doctree-read`` callback that drops ``attr`` from the doctree.

    Per-document runners live as attributes on ``state.document`` so they
    persist across directives of the same page. Without a cleanup, the runner
    namespace would leak into the pickled doctree.
    """

    def cleanup(app: Sphinx, doctree: nodes.document) -> None:
        if getattr(doctree, attr, None) is not None:
            delattr(doctree, attr)

    cleanup.__name__ = f"cleanup_{attr}"
    cleanup.__qualname__ = cleanup.__name__
    return cleanup


class StatelessDomain(Domain):
    """:class:`~sphinx.domains.Domain` base for directive-only domains.

    Sphinx requires :meth:`merge_domaindata` on any domain declaring
    ``parallel_read_safe = True``, and MyST-Parser warns when
    :meth:`resolve_any_xref` is missing.
    """

    def merge_domaindata(
        self, docnames: t.AbstractSet[str], otherdata: dict[str, t.Any]
    ) -> None:
        """No-op: stateless, safe to run in parallel."""

    def resolve_any_xref(
        self,
        env: BuildEnvironment,
        fromdocname: str,
        builder: Builder,
        target: str,
        node: pending_xref,
        contnode: Element,
    ) -> list[tuple[str, nodes.reference]]:
        """No-op: this domain provides no objects to cross-reference."""
        return []
