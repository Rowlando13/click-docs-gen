# click-docs-gen

Utilities for automatically documenting [Click] applications.

[Click]: https://click.palletsprojects.com/

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
