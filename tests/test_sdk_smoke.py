from pathlib import Path

import p2s
from p2s import P2S


def test_public_api():
    assert p2s.__version__ == "1.2.0"
    assert P2S is p2s.P2SClient


def test_load_example_config():
    sdk = P2S.from_toml("configs/aitasker.toml", workdir=".tmp-test")
    assert sdk.config.target.name
    assert Path(sdk.workdir).is_absolute()
