import os

from pipeline.config import load_config, long_path, merge_config


def test_local_overlay_replaces_sources_and_extends_allowlist():
    base = {"sources": [{"name": "a", "path": "Sources/a"}], "llm": {"model": "m1", "url": "http://localhost:11434"},
            "allowlist": {"terms": ["Alpha"], "no_bare_match": ["Page"]}}
    local = {"sources": [{"name": "b", "path": "Sources/b"}], "llm": {"model": "m2"},
             "allowlist": {"terms": ["Beta", "Alpha"], "no_bare_match": ["Town"]}}
    cfg = merge_config(base, local)
    assert cfg["sources"] == [{"name": "b", "path": "Sources/b"}]
    assert cfg["llm"] == {"model": "m2", "url": "http://localhost:11434"}
    assert cfg["allowlist"] == {"terms": ["Alpha", "Beta"], "no_bare_match": ["Page", "Town"]}
    assert base["allowlist"]["terms"] == ["Alpha"]   # the shared config is not modified


def test_missing_local_file_is_ignored(tmp_path):
    shared = tmp_path / "pipeline.toml"
    shared.write_text('[output]\ndir = "filtered"\n', encoding="utf-8")
    assert load_config(shared, tmp_path / "local.toml") == {"output": {"dir": "filtered"}}


def test_long_path_prefix_only_on_windows(tmp_path):
    p = long_path(tmp_path)
    assert p.startswith("\\\\?\\") == (os.name == "nt")
