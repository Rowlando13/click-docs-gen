# Copied directly from click-extra. For click internal use only.
"""Sphinx extension providing the ``click:source`` and ``click:run`` directives.

Add ``click_docs_gen.sphinx`` to ``extensions`` in ``conf.py``, and opt in to
build-time code execution with ``click_docs_gen_enable_exec_directives = True``.

.. danger::

    Both directives execute arbitrary Python at build time with the full
    privileges of the Sphinx process. They are disabled by default.
"""

from __future__ import annotations

import typing as t
from importlib.metadata import version

from sphinx.util import logging

from .click import cleanup_runner
from .click import ClickDomain

if t.TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.config import Config
    from sphinx.util.typing import ExtensionMetadata

logger: logging.SphinxLoggerAdapter = logging.getLogger(__name__)

EXEC_DIRECTIVES_OPT_IN = "click_docs_gen_enable_exec_directives"
"""Name of the ``conf.py`` value enabling the ``click:*`` directives."""


def _register_exec_directives(app: Sphinx, config: Config) -> None:
    """Register :class:`ClickDomain` if ``conf.py`` opts in."""
    if not getattr(config, EXEC_DIRECTIVES_OPT_IN, False):
        logger.info(
            "click_docs_gen.sphinx: click:* directives are disabled. Set %s = "
            "True in conf.py to enable build-time code execution.",
            EXEC_DIRECTIVES_OPT_IN,
        )
        return

    app.add_domain(ClickDomain)
    app.connect("doctree-read", cleanup_runner)


def setup(app: Sphinx) -> ExtensionMetadata:
    """Register the extension with Sphinx."""
    app.add_config_value(EXEC_DIRECTIVES_OPT_IN, False, "env", types=(bool,))
    app.connect("config-inited", _register_exec_directives)
    return {
        "version": version("click-docs-gen"),
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
