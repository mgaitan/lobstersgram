# Working with This Workspace

Lobstergram is a uv-managed Python workspace. Keep changes small, preserve the
boundaries between the application and reusable packages, and run the checks
that cover the code you touched.

This file is adapted from the [python-package-copier-template AGENTS.md](https://github.com/mgaitan/python-package-copier-template/blob/main/AGENTS.md).

## Workspace Layout

- `src/lobstergram/` contains the main Telegram application and its
  `lobstergram` command-line entrypoint.
- `packages/md-to-telegraph/` contains the reusable Markdown-to-Telegraph
  package.
- `packages/url-to-markdown/` contains the reusable URL/HTML-to-Markdown
  package.
- Each child package has its own `pyproject.toml`, metadata, dependencies,
  version, `README.md`, `src/<import_name>/`, and package-local tests.
- The root `pyproject.toml` owns workspace membership and shared Ruff, pytest,
  and coverage configuration. `uv.lock` is shared by the workspace.
- Root `tests/` covers the application; tests for a reusable package belong in
  that package's `tests/` directory.

## Common Commands

```bash
uv sync
uv run lobstergram --help
uv run pytest -q
uv run pytest packages/url-to-markdown/tests/test_html.py
uv run ruff check .
uv run ruff format --check .
uv build --all-packages
```

The default coverage gate measures `md_to_telegraph` and `url_to_markdown` at
100%. The application tests run in the same pytest invocation, but the root
configuration does not currently enforce 100% coverage for `lobstergram`.

## Package Boundaries

- Keep Telegram orchestration, configuration, persistence, and runtime state
  in `src/lobstergram/`.
- Keep reusable conversion and extraction logic in the relevant child package.
- Reusable packages should not import application modules from `lobstergram`.
- Put shared QA configuration in the root `pyproject.toml`; keep package
  metadata and package-specific runtime dependencies in the child package's
  `pyproject.toml`.

## Releases

Packages are versioned and released independently. Bump a package from the
workspace root, for example:

```bash
uv version --package url-to-markdown --bump patch
uv lock
git tag url-to-markdown-v<version>
git push origin url-to-markdown-v<version>
```

Use the package names `lobstergram`, `md-to-telegraph`, or
`url-to-markdown`. The `cd.yml` workflow builds and publishes only the package
selected by its tag.

## Editing and Verification

- Use `apply_patch` for manual edits.
- Do not manually edit `uv.lock`; regenerate it with `uv lock` after dependency
  or version changes.
- Do not overwrite runtime state files such as `state.json`, subscribers,
  message maps, or bookmarks unless the task explicitly requires it.
- Never discard unrelated user changes with destructive git commands.
- Before handing off a change, run the narrowest useful tests plus `ruff check`;
  for dependency, packaging, or workspace changes also run `uv build --all-packages`.
