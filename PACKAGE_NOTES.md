# P2S Framework Package Notes

This repository was reconstructed from `p2s_framework.md` into the concrete file layout documented by the technical reference.

## Included

- `p2s/` implementation package: proxy, compiler, engine, adapters, dataset builder, and analytics suite.
- `p2s_runner.py`: unified 9-mode CLI.
- `configs/seal_hackathon.toml` and `configs/aitasker.toml`.
- `hooks/seal_setup_hook.py`.
- `README.md` and `docs/P2S_FRAMEWORK_REFERENCE.md`: the full supplied unified technical reference.
- `.gitignore` for Python/build/runtime artifacts.

## Packaging correction

The supplied `pyproject.toml` exposes `p2s = "p2s_runner:main"` but its setuptools package discovery originally included only `p2s` packages. This package adds:

```toml
[tool.setuptools]
py-modules = ["p2s_runner"]
```

so the documented installed `p2s` console command works. No framework behavior was otherwise changed from the supplied implementation blocks.

## Validation performed

- `python -m compileall -q .` — passed.
- Imported `p2s_runner` — passed.
- Parsed both TOML configurations with `tomllib` — passed.
- Editable install with `pip install -e . --no-deps --no-build-isolation` — passed in the build environment.
- `p2s --help` — passed and exposed all 9 documented modes.

## Deliberately not included

The reference explicitly says the Colab A100 SFT notebook/script `p2s_colab_train.py` is distributed separately and is not part of the document, so it is not fabricated here.
