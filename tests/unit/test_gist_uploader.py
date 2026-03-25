"""Unit tests for gist_uploader.py — GitHub Gist upload for Open in Colab."""
import json
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))

from gist_uploader import upload_gist, _build_colab_url


SAMPLE_NB = b'{"nbformat": 4, "cells": []}'
VALID_TOKEN = "ghp_testtoken123"
GIST_ID = "abc123def456"
OWNER_LOGIN = "testuser"


# ── _build_colab_url ─────────────────────────────────────────────────────────

def test_build_colab_url_format():
    url = _build_colab_url(OWNER_LOGIN, GIST_ID)
    assert url == f"https://colab.research.google.com/gist/{OWNER_LOGIN}/{GIST_ID}"


def test_build_colab_url_different_user():
    url = _build_colab_url("another_user", "xyz999")
    assert url == "https://colab.research.google.com/gist/another_user/xyz999"


# ── upload_gist success ──────────────────────────────────────────────────────

def _make_mock_response(status_code=201, body=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = body or {
        "id": GIST_ID,
        "owner": {"login": OWNER_LOGIN},
        "html_url": f"https://gist.github.com/{OWNER_LOGIN}/{GIST_ID}",
    }
    return mock


def test_upload_gist_returns_colab_url():
    with patch("gist_uploader.httpx.post") as mock_post:
        mock_post.return_value = _make_mock_response()
        result = upload_gist(SAMPLE_NB, VALID_TOKEN)
    assert result == f"https://colab.research.google.com/gist/{OWNER_LOGIN}/{GIST_ID}"


def test_upload_gist_posts_to_correct_url():
    with patch("gist_uploader.httpx.post") as mock_post:
        mock_post.return_value = _make_mock_response()
        upload_gist(SAMPLE_NB, VALID_TOKEN)
    call_args = mock_post.call_args
    assert "api.github.com/gists" in call_args[0][0]


def test_upload_gist_sends_authorization_header():
    with patch("gist_uploader.httpx.post") as mock_post:
        mock_post.return_value = _make_mock_response()
        upload_gist(SAMPLE_NB, VALID_TOKEN)
    headers = mock_post.call_args[1]["headers"]
    assert headers["Authorization"] == f"Bearer {VALID_TOKEN}"


def test_upload_gist_sends_notebook_content():
    with patch("gist_uploader.httpx.post") as mock_post:
        mock_post.return_value = _make_mock_response()
        upload_gist(SAMPLE_NB, VALID_TOKEN)
    body = mock_post.call_args[1]["json"]
    files = body["files"]
    assert "notebook.ipynb" in files
    assert files["notebook.ipynb"]["content"] == SAMPLE_NB.decode("utf-8")


def test_upload_gist_is_public():
    with patch("gist_uploader.httpx.post") as mock_post:
        mock_post.return_value = _make_mock_response()
        upload_gist(SAMPLE_NB, VALID_TOKEN)
    body = mock_post.call_args[1]["json"]
    assert body["public"] is True


def test_upload_gist_has_description():
    with patch("gist_uploader.httpx.post") as mock_post:
        mock_post.return_value = _make_mock_response()
        upload_gist(SAMPLE_NB, VALID_TOKEN)
    body = mock_post.call_args[1]["json"]
    assert "description" in body
    assert len(body["description"]) > 0


# ── upload_gist error handling ───────────────────────────────────────────────

def test_upload_gist_raises_on_401():
    with patch("gist_uploader.httpx.post") as mock_post:
        mock = MagicMock()
        mock.status_code = 401
        mock.text = "Bad credentials"
        mock_post.return_value = mock
        with pytest.raises(RuntimeError, match="401"):
            upload_gist(SAMPLE_NB, "bad-token")


def test_upload_gist_raises_on_422():
    with patch("gist_uploader.httpx.post") as mock_post:
        mock = MagicMock()
        mock.status_code = 422
        mock.text = "Unprocessable Entity"
        mock_post.return_value = mock
        with pytest.raises(RuntimeError, match="422"):
            upload_gist(SAMPLE_NB, VALID_TOKEN)


def test_upload_gist_raises_on_network_error():
    with patch("gist_uploader.httpx.post") as mock_post:
        mock_post.side_effect = Exception("Network timeout")
        with pytest.raises(Exception, match="Network timeout"):
            upload_gist(SAMPLE_NB, VALID_TOKEN)


def test_upload_gist_uses_accept_header():
    with patch("gist_uploader.httpx.post") as mock_post:
        mock_post.return_value = _make_mock_response()
        upload_gist(SAMPLE_NB, VALID_TOKEN)
    headers = mock_post.call_args[1]["headers"]
    assert "application/vnd.github" in headers.get("Accept", "")
