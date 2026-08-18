# Historical / Original Reproducibility Archive

This directory is a **frozen audit archive** of the one-off procedures and helper files used while the P2S research system evolved.

It is no longer the primary reproduction path.

Use the repository's top-level `docs/` directory for P2S Framework v1.2 reproduction, where the shared package implements proxying/compilation/state orchestration/fuzzing rather than switching among historical `trace_compiler.py`, `eval_student_p2s_engine.py`, and target-specific proxy variants.

The archive remains useful for:

- validating that a v1.2 TOML field faithfully represents an original workaround;
- inspecting exact historical command sequences;
- auditing post-hoc scripts and source-derived fixes;
- explaining differences between the development artifact and normalized framework.

Do not treat an old model/provider placeholder as authoritative when it conflicts with the final retained experiment. In particular, the completed AutoRestTest Track-A experiment used **DeepSeek-V4-Flash**.
