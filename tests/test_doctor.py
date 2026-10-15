import pytest

from pipeline.doctor import GB, choose_model, model_budget
from pipeline.llm import LLMError, require_local


def test_prefers_best_installed_model_that_fits():
    m, have = choose_model({"gemma4:12b": {}, "qwen3:14b": {}}, 16 * GB)
    assert (m["name"], have) == ("qwen3:14b", True)
    m, have = choose_model({"gemma4:12b": {}, "qwen3:14b": {}}, 10 * GB)
    assert (m["name"], have) == ("gemma4:12b", True)


def test_installed_recommended_model_used_even_if_it_spills_to_cpu():
    m, have = choose_model({"qwen3:14b": {}, "granite4.2:8b": {}}, 8 * GB)
    assert (m["name"], have) == ("qwen3:14b", True)


def test_suggests_without_installing_when_nothing_suitable():
    m, have = choose_model({"granite4.2:8b": {}, "llama3.2:latest": {}}, 24 * GB)
    assert (m["name"], have) == ("qwen3:14b", False)
    m, have = choose_model({}, 0)   # CPU only: still the most accurate model, never a weaker one
    assert (m["name"], have) == ("qwen3:14b", False)


def test_budget_by_platform():
    assert model_budget([("Intel", "UHD Graphics", 2 * GB)], 32 * GB)[0] == 0
    assert model_budget([("NVIDIA", "RTX 4070", 12 * GB), ("Intel", "UHD", GB)], 32 * GB)[0] == 12 * GB
    assert model_budget([("Apple", "Apple M3", 32 * GB)], 32 * GB)[0] == int(32 * GB * 0.66)


@pytest.mark.parametrize("url", ["http://localhost:11434", "http://127.0.0.1:11434/", "http://[::1]:11434"])
def test_local_llm_urls_accepted(url):
    assert require_local(url) == url.rstrip("/")


@pytest.mark.parametrize("url", ["http://192.168.1.20:11434", "https://ollama.example.com", "http://localhost.evil.com"])
def test_remote_llm_urls_refused(url):
    with pytest.raises(LLMError):
        require_local(url)
