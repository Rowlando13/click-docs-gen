# Copied directly from click-extra. For click internal use only.
"""Runner executing the bodies of the ``click:*`` directives.

:class:`ClickRunner` runs every block of a document in one shared namespace,
and returns what a terminal would show for it: the invocations, the input and
the output.
"""

from __future__ import annotations

import ast
import contextlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import typing as t
from functools import partial

import click
from click.testing import CliRunner
from click.testing import EchoingStdin
from click.testing import Result

from ._base import compile_directive
from ._base import directive_source
from ._base import PLACEHOLDER_FILE

if t.TYPE_CHECKING:
    from collections.abc import Generator
    from collections.abc import Iterator
    from collections.abc import Mapping
    from collections.abc import Sequence

    from ._base import ContentOffsetMixin

PROMPT_SIGIL = "$"
"""Sigil drawn before each command a block runs."""

_INTERPRETER_RE = re.compile(r"(?:^|/)(?:python|pypy)[\d.]*$")
"""Match the first word of a command line that only *runs* a program."""


class TerminatedEchoingStdin(EchoingStdin):
    r"""Like :class:`click.testing.EchoingStdin` but echoes a visible ``^D`` in
    place of the EOT character (``\x04``).

    :meth:`ClickRunner.invoke` adds ``\x04`` when ``terminate_input=True``.
    """

    def _echo(self, rv: bytes) -> bytes:
        eof = rv.endswith(b"\x04")

        if eof:
            rv = rv[:-1]

        if not self._paused:
            self._output.write(rv)

            if eof:
                self._output.write(b"^D\n")

        return rv


@contextlib.contextmanager
def patch_attr(obj: object, name: str, value: t.Any) -> Iterator[None]:
    """Temporarily set ``obj.name`` to ``value``, restoring the original on exit."""
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


@contextlib.contextmanager
def patch_subprocess() -> Iterator[None]:
    """Redirect ``subprocess.call`` output to ``click.echo``.

    The patch is process-global, so a parallel reader running another
    document at the same time sees it too.
    """

    def dummy_call(*args: t.Any, **kwargs: t.Any) -> int:
        with tempfile.TemporaryFile("wb+") as f:
            kwargs["stdout"] = f
            kwargs["stderr"] = f
            rv = subprocess.Popen(*args, **kwargs).wait()
            f.seek(0)
            click.echo(f.read().decode("utf-8", "replace").rstrip())
        return rv

    with patch_attr(subprocess, "call", dummy_call):
        yield


@contextlib.contextmanager
def isolated_filesystem(
    temp_dir: str | os.PathLike[str] | None = None,
) -> Iterator[str]:
    """Create a temporary directory and change the working directory to it.

    :param temp_dir: create the temporary directory inside this one. When
        given, the directory is left in place on exit.
    """
    target = tempfile.mkdtemp(dir=temp_dir)
    try:
        with contextlib.chdir(target):
            yield target
    finally:
        if temp_dir is None:
            shutil.rmtree(target, ignore_errors=True)


def format_cli_prompt(
    cmd_args: Sequence[str],
    extra_env: Mapping[str, str | None] | None = None,
) -> str:
    """Render the shell line a reader would type to run ``cmd_args``.

    The program name is left as is, every other token is shell-quoted.
    Environment variables mapped to ``None`` are unset with ``env -u``.
    """
    parts = [PROMPT_SIGIL]
    if extra_env:
        unset = [name for name, value in extra_env.items() if value is None]
        if unset:
            parts.append("env")
            for name in unset:
                parts.extend(("-u", name))
        parts.extend(
            f"{name}={shlex.quote(value)}"
            for name, value in extra_env.items()
            if value is not None
        )
    program, *args = cmd_args
    parts.append(program)
    parts.extend(shlex.quote(arg) for arg in args)
    return " ".join(parts)


def program_from_command_line(command_line: str) -> str:
    """The program name Click is given for a command line a block displays.

    Only an interpreter prefix like ``python -m`` is dropped, since it names no
    program.
    """
    first, _, rest = command_line.partition(" ")
    if rest and _INTERPRETER_RE.search(first):
        return command_line.rsplit(" ", 1)[-1]
    return command_line


class ClickRunner(CliRunner):
    """A :class:`click.testing.CliRunner` for Sphinx directive execution."""

    def __init__(self) -> None:
        super().__init__(echo_stdin=True)
        self.namespace: dict[str, t.Any] = {
            "click": click,
            "__file__": PLACEHOLDER_FILE,
        }

    @contextlib.contextmanager
    def isolation(
        self,
        input: str | bytes | t.IO[t.Any] | None = None,
        env: Mapping[str, str | None] | None = None,
        color: bool = False,
    ) -> Generator[tuple[t.Any, ...], None, None]:
        """Echo a ``^D`` marker at the end of the isolated stdin."""
        with super().isolation(input=input, env=env, color=color) as streams:
            # Click wraps the echoing buffer in the text stream bound to
            # sys.stdin, so the wrapper is the only handle on it.
            sys.stdin.buffer.__class__ = TerminatedEchoingStdin
            yield streams

    def invoke(  # type: ignore[override]
        self,
        cli: click.Command,
        args: str | Sequence[str] | None = None,
        prog_name: str | None = None,
        input: str | bytes | Sequence[str] | None = None,
        terminate_input: bool = False,
        env: Mapping[str, str | None] | None = None,
        _output_lines: list[str] | None = None,
        _show_prompt: bool = True,
        **extra: t.Any,
    ) -> Result:
        """Like :meth:`click.testing.CliRunner.invoke`, but also records what
        the user would see in the terminal: env vars, command line, prompts.

        :param terminate_input: Whether to display ``^D`` after a list of input.
        :param _output_lines: Internal list collecting the lines to display.
        :param _show_prompt: Whether to draw the invocation above the output.
        """
        output_lines = _output_lines if _output_lines is not None else []

        if args is None:
            args = []
        elif isinstance(args, str):
            args = shlex.split(args)

        if prog_name is None:
            prog_name = (cli.name or "cli").replace("_", "-")

        if _show_prompt:
            output_lines.append(
                format_cli_prompt(
                    (prog_name, *args),
                    extra_env=dict(sorted(env.items())) if env else None,
                )
            )
        prog_name = program_from_command_line(prog_name)

        if isinstance(input, (tuple, list)):
            input = "\n".join(input) + "\n"

            if terminate_input:
                input += "\x04"

        result = super().invoke(
            cli=cli,
            args=args,
            input=t.cast("str | bytes | None", input),
            env=env,
            prog_name=prog_name,
            **extra,
        )
        output_lines.extend(result.output.splitlines())
        return result

    def execute_source(self, directive: ContentOffsetMixin) -> list[str]:
        """Execute the given code, adding it to the runner's namespace."""
        code = compile_directive(directive)
        with patch_subprocess():
            exec(code, self.namespace)
        return []

    def run_cli(self, directive: ContentOffsetMixin) -> list[str]:
        """Execute the body of ``directive`` and return what a terminal shows.

        The body can call these functions without importing them:

        - ``invoke()``: same as :meth:`ClickRunner.invoke`.
        - ``isolated_filesystem()``: context manager changing to a temporary
          directory while executing the block.

        :raises RuntimeError: when the body assigns a variable named like one
            of these functions.
        """
        source_code, location = directive_source(directive)

        buffer: list[str] = []

        local_vars: dict[str, t.Any] = {
            "invoke": partial(
                self.invoke,
                _output_lines=buffer,
                _show_prompt=getattr(directive, "show_prompt", True),
            ),
            "isolated_filesystem": isolated_filesystem,
        }

        tree = ast.parse(source_code, location)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Store)
                and node.id in local_vars
            ):
                python_line = source_code.splitlines()[node.lineno - 1]
                doc_lineno = directive.abs_content_offset + node.lineno
                raise RuntimeError(
                    f"Local variable {node.id!r} at "
                    f"{location}:{directive.name}:{doc_lineno} conflicts with "
                    f"the one automatically provided by the {directive.name} "
                    "directive.\n"
                    f"Line: {python_line}"
                )

        exec(compile(tree, location, "exec"), self.namespace, local_vars)
        return buffer
