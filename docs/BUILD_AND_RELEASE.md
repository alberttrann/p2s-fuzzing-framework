```text
source code + pyproject.toml
          │
          │ python -m build
          ▼
      build/              temporary/intermediate workspace
          │
          ▼
       dist/              final distributable files
          ├── p2s_framework-1.2.0-py3-none-any.whl
          └── p2s_framework-1.2.0.tar.gz   # when an sdist is built
```

`*.egg-info/` is also generated packaging metadata.

None of these directories is the authoritative source code.

---

## 1. Normal user installation does not require `build/`

A wheel user only needs:

```text
p2s_framework-1.2.0-py3-none-any.whl
```

Install it with:

```bash
python -m pip install ./p2s_framework-1.2.0-py3-none-any.whl
```

You can delete `build/` without breaking the installed package.

---

## 2. Source users do not need a wheel at all

From the repository root:

```bash
python -m pip install -e .
```

`pip` reads `pyproject.toml`, installs runtime dependencies, creates package metadata, and exposes the `p2s` console command.

Editable install is the normal choice while modifying the framework.

---

## 3. Build a wheel yourself

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run tests:

```bash
python -m compileall -q p2s tests
python -m pytest -q
```

Build:

```bash
python -m build
```

or wheel only:

```bash
python -m build --wheel
```

The final file appears under `dist/`.

In an offline environment where build isolation cannot download build requirements, use:

```bash
python -m build --wheel --no-isolation
```

provided the build requirements are already installed.

---

## 4. Clean generated packaging files

Git Bash / Linux / macOS:

```bash
rm -rf build dist *.egg-info
find . -type d -name __pycache__ -prune -exec rm -rf {} +
```

PowerShell:

```powershell
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Get-ChildItem -Directory -Filter "*.egg-info" | Remove-Item -Recurse -Force
```

Then rebuild from source whenever needed.

Recommended repository practice:

- **do not commit `build/`**;
- **do not normally commit `*.egg-info/`**;
- usually **do not commit `dist/`** either;
- publish the wheel as a GitHub Release asset (or package index artifact);
- keep `pyproject.toml`, `p2s/`, configs, docs, and tests as the source of truth.

This research release bundle intentionally contains a `dist/` copy so a reviewer can install the exact packaged SDK without rebuilding it. That convenience artifact does not make `dist/` part of the framework implementation.

The repository `.gitignore` should therefore include:

```gitignore
build/
dist/
*.egg-info/
```

## 5. Verify a built wheel

Create a fresh environment rather than trusting the development environment:

```bash
python -m venv /tmp/p2s-wheel-check
source /tmp/p2s-wheel-check/bin/activate
python -m pip install dist/p2s_framework-1.2.0-py3-none-any.whl
python -c "import p2s; print(p2s.__version__)"
p2s --help
```

Windows Git Bash equivalent:

```bash
python -m venv .wheel-check
source .wheel-check/Scripts/activate
python -m pip install dist/p2s_framework-1.2.0-py3-none-any.whl
```

---

## 6. Release checklist

Before publishing:

```text
[ ] tests pass
[ ] README links resolve
[ ] docs describe the current package, not historical helper forks
[ ] version in pyproject.toml matches p2s.__version__
[ ] wheel installs in a clean venv
[ ] p2s --help works
[ ] no credentials/tokens are included
[ ] generated caches/build intermediates are cleaned
[ ] SHA-256 checksum is recorded for release artifacts
```
