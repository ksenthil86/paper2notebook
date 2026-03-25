"""Task 1 — Smoke tests: verify backend app structure is correct."""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))


def test_app_importable():
    """FastAPI app can be imported without errors."""
    from main import app
    assert app is not None


def test_app_is_fastapi():
    """App object is a FastAPI instance."""
    from fastapi import FastAPI
    from main import app
    assert isinstance(app, FastAPI)


def test_app_has_title():
    """App has a meaningful title."""
    from main import app
    assert app.title and len(app.title) > 0


def test_requirements_file_exists():
    """requirements.txt exists in backend/."""
    req_path = os.path.join(os.path.dirname(__file__), "../../backend/requirements.txt")
    assert os.path.exists(req_path), "requirements.txt missing"


def test_requirements_has_core_deps():
    """requirements.txt includes fastapi, uvicorn, pdfplumber, openai, nbformat."""
    req_path = os.path.join(os.path.dirname(__file__), "../../backend/requirements.txt")
    content = open(req_path).read().lower()
    for dep in ["fastapi", "uvicorn", "pdfplumber", "openai", "nbformat"]:
        assert dep in content, f"Missing dependency: {dep}"


def test_env_example_exists():
    """`.env.example` exists at project root."""
    env_path = os.path.join(os.path.dirname(__file__), "../../.env.example")
    assert os.path.exists(env_path), ".env.example missing"


def test_frontend_package_json_exists():
    """frontend/package.json exists."""
    pkg_path = os.path.join(os.path.dirname(__file__), "../../frontend/package.json")
    assert os.path.exists(pkg_path), "frontend/package.json missing"


def test_frontend_has_dev_script():
    """frontend/package.json has a 'dev' script."""
    import json
    pkg_path = os.path.join(os.path.dirname(__file__), "../../frontend/package.json")
    pkg = json.load(open(pkg_path))
    assert "dev" in pkg.get("scripts", {}), "No 'dev' script in package.json"


def test_frontend_src_files_exist():
    """frontend/src/main.jsx and App.jsx exist."""
    base = os.path.join(os.path.dirname(__file__), "../../frontend/src")
    assert os.path.exists(os.path.join(base, "main.jsx")), "main.jsx missing"
    assert os.path.exists(os.path.join(base, "App.jsx")), "App.jsx missing"
