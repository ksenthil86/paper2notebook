"""Task 10 — Tests for README.md content requirements."""
import os
import re

README_PATH = os.path.join(os.path.dirname(__file__), "../../README.md")


def _readme() -> str:
    with open(README_PATH, "r") as f:
        return f.read()


def test_readme_exists():
    assert os.path.isfile(README_PATH), "README.md does not exist"


def test_readme_has_python_prerequisite():
    content = _readme().lower()
    assert "python" in content
    # Must mention 3.10 or higher
    assert re.search(r"python\s*3\.[1-9][0-9]+", content) or "3.10" in content


def test_readme_has_node_prerequisite():
    content = _readme().lower()
    assert "node" in content
    assert re.search(r"node\s*1[89]", content) or "18" in content


def test_readme_has_backend_install_instructions():
    content = _readme().lower()
    # Should mention pip install or requirements.txt
    assert "pip install" in content or "requirements.txt" in content


def test_readme_has_frontend_install_instructions():
    content = _readme().lower()
    assert "npm install" in content


def test_readme_has_backend_run_instructions():
    content = _readme()
    # Should mention uvicorn
    assert "uvicorn" in content


def test_readme_has_frontend_run_instructions():
    content = _readme().lower()
    # Should mention npm run dev
    assert "npm run dev" in content


def test_readme_has_openai_api_key_info():
    content = _readme().lower()
    assert "openai" in content
    assert "api key" in content


def test_readme_has_open_in_colab_section():
    content = _readme().lower()
    assert "colab" in content
    assert "github" in content


def test_readme_has_model_fallback_note():
    content = _readme().lower()
    # Should mention the model fallback chain
    assert "fallback" in content or "gpt-4" in content or "o3" in content


def test_readme_has_env_example_reference():
    content = _readme()
    assert ".env" in content


def test_readme_title_mentions_paper2notebook():
    content = _readme().lower()
    assert "paper2notebook" in content or "paper to notebook" in content or "paper → notebook" in content
