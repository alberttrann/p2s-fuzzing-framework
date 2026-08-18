import json
from pathlib import Path

from p2s import P2S
from p2s.compiler.compiler import P2SCompiler
from p2s.config import load_config


def test_all_research_configs_parse():
    for path in Path("configs/research").rglob("*.toml"):
        cfg = load_config(str(path))
        assert cfg.target.name


def test_track_b_uses_external_fixture_trace_freeze(tmp_path, monkeypatch):
    root = tmp_path / "restgym"
    root.mkdir()
    fixture = root / "p2s_traces" / "blog" / "primitive_traces.jsonl"
    fixture.parent.mkdir(parents=True)
    fixture.write_text('{"flow_id":"f","step":1,"request":{},"response":{}}\n', encoding="utf-8")
    monkeypatch.setenv("RESTGYM_ROOT", str(root))

    cfg = tmp_path / "record.toml"
    cfg.write_text(
        f'''[target]\nname="x"\nbase_url="http://localhost"\nopenapi_spec="spec.json"\n\n'''
        '''[llm]\n\n[proxy]\noutput_file="proxy.jsonl"\n\n'''
        f'''[research]\nroot_dir="{root.as_posix()}"\nrecord_command="python -c \\\"print('recorded')\\\""\nrecord_trace_source="p2s_traces/blog/primitive_traces.jsonl"\nrecord_snapshot_file="baseline.jsonl"\n''',
        encoding="utf-8",
    )
    sdk = P2S.from_toml(str(cfg), workdir=tmp_path / "run")
    sdk.record()
    frozen = tmp_path / "run" / "baseline.jsonl"
    assert frozen.read_text(encoding="utf-8") == fixture.read_text(encoding="utf-8")


def test_compiler_yaml_and_form_urlencoded(tmp_path):
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        '''openapi: 3.0.0\npaths:\n  /constraints/requires:\n    post:\n      requestBody:\n        content:\n          application/x-www-form-urlencoded:\n            schema:\n              type: object\n              properties:\n                feature:\n                  type: string\n                requires:\n                  type: string\n      responses:\n        '200': {description: ok}\n''',
        encoding="utf-8",
    )
    primitive = tmp_path / "primitive.jsonl"
    primitive.write_text(json.dumps({
        "flow_id": "f", "step": 1,
        "request": {
            "method": "POST", "path": "/constraints/requires",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": "feature=a&requires=b",
        },
        "response": {"status_code": 200, "body": {}},
    }) + "\n", encoding="utf-8")
    out = tmp_path / "compiled.jsonl"
    catalog = tmp_path / "catalog.json"
    P2SCompiler(str(spec), context_path_prefix="").compile(str(primitive), str(out), str(catalog))
    row = json.loads(out.read_text(encoding="utf-8"))
    assert "--feature a" in row["ocli_command"]
    assert "--requires b" in row["ocli_command"]


def test_baseline_patch_regex_is_idempotent(tmp_path):
    root = tmp_path / "seal"
    java1 = root / "src/main/java/vn/edu/fpt/seal/config/AppProperties.java"
    java2 = root / "src/main/java/vn/edu/fpt/seal/security/JwtService.java"
    java1.parent.mkdir(parents=True)
    java2.parent.mkdir(parents=True)
    java1.write_text("private int accessTokenExpirationMinutes = 60;\n", encoding="utf-8")
    java2.write_text("Instant exp = now.plus(60, ChronoUnit.MINUTES);\n", encoding="utf-8")

    text = Path("configs/research/track_a_baselines.toml").read_text(encoding="utf-8")
    text = text.replace('root_dir = "$SEAL_ROOT"', f'root_dir = "{root.as_posix()}"')
    cfg = tmp_path / "baseline.toml"
    cfg.write_text(text, encoding="utf-8")
    sdk = P2S.from_toml(str(cfg), workdir=tmp_path / "run")
    first = sdk.patch()
    second = sdk.patch()
    assert any(r.changed for r in first)
    assert all(not r.changed for r in second)
    assert "525600" in java1.read_text(encoding="utf-8")
    assert "525600" in java2.read_text(encoding="utf-8")


def test_strict_fd_filters_2xx_before_dedup(tmp_path):
    from p2s.analytics.faults import deduplicate_5xx_faults
    p = tmp_path / "goldens.jsonl"
    rows = [
        {"endpoint": "ocli a", "actual_status": 500, "messages": [{"content": "status code 500 FooError"}]},
        {"endpoint": "ocli a", "actual_status": 500, "messages": [{"content": "status code 500 FooError"}]},
        {"endpoint": "ocli a", "actual_status": 200, "messages": [{"content": "status code 200 bypass"}]},
    ]
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    out = tmp_path / "dedup.jsonl"
    result = deduplicate_5xx_faults(str(p), str(out))
    assert result["raw_goldens"] == 3
    assert result["raw_5xx_records"] == 2
    assert result["unique_5xx_signatures"] == 1
    assert result["excluded_non_5xx_goldens"] == 1


def test_aitasker_seed_runs_from_backend_directory():
    cfg = load_config("configs/research/aitasker_training.toml")
    assert cfg.postgres is not None
    assert cfg.postgres.seed_command.startswith("cd backend && ")
    assert "prisma/migrations/010_seed.sql" in cfg.postgres.seed_command


def test_framework_native_docs_split_and_autoresttest_source_of_truth():
    root = Path('.')
    assert (root / 'docs' / 'REPRODUCIBILITY.md').exists()
    assert (root / 'original_reporducibility_docs' / 'REPRODUCIBILITY.md').exists()
    primary = (root / 'docs' / 'REPRODUCIBILITY.md').read_text(encoding='utf-8')
    track_a = (root / 'docs' / 'TRACK_A_WITH_P2S_FRAMEWORK.md').read_text(encoding='utf-8')
    archive = (root / 'original_reporducibility_docs' / 'README.md').read_text(encoding='utf-8')
    assert 'one public implementation of P2S' in primary
    assert 'DeepSeek-V4-Flash' in track_a
    assert 'DeepSeek-V4-Flash' in archive


def test_all_track_b_framework_profiles_present():
    expected = {
        'blog', 'erc20', 'features-service', 'flight-search', 'gestao-hospital',
        'kafka-rest-proxy', 'market', 'notebook-manager', 'person-controller',
        'pet-clinic', 'project-tracking-system',
    }
    found = {p.stem for p in Path('configs/research/track_b').glob('*.toml')}
    assert found == expected
