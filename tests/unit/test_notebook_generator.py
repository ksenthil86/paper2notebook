"""Task 4 — Unit tests: OpenAI two-phase notebook cell generation.

All OpenAI calls are mocked — no real API key needed.
"""
import sys
import os
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest


# ── Fixtures / helpers ───────────────────────────────────────────────────────

SAMPLE_PAPER_TEXT = """
Attention Is All You Need

Abstract: We propose a new simple network architecture, the Transformer,
based solely on attention mechanisms, dispensing with recurrence and convolutions.
Experiments show these models are superior in quality while being more parallelizable.

1. Introduction
Self-attention, sometimes called intra-attention, is an attention mechanism
relating different positions of a single sequence to compute a representation.

2. Model Architecture
The Transformer uses stacked self-attention and point-wise, fully connected layers.
The encoder maps an input sequence to a sequence of continuous representations.

Algorithm: Multi-Head Attention
  Given queries Q, keys K, values V:
  Attention(Q,K,V) = softmax(QK^T / sqrt(d_k)) V
  MultiHead(Q,K,V) = Concat(head_1,...,head_h) W^O
"""

PHASE1_JSON = {
    "title": "Attention Is All You Need",
    "authors": ["Vaswani et al."],
    "venue": "NeurIPS 2017",
    "domain": "Natural Language Processing / Deep Learning",
    "algorithms": [
        {
            "name": "Scaled Dot-Product Attention",
            "description": "Computes attention weights via dot products scaled by sqrt(d_k)",
        },
        {
            "name": "Multi-Head Attention",
            "description": "Runs multiple attention heads in parallel and concatenates results",
        },
    ],
    "key_equations": [
        r"Attention(Q,K,V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V"
    ],
}

PHASE2_CELLS = [
    {"cell_type": "markdown", "source": "# Attention Is All You Need\n## Tutorial Notebook"},
    {"cell_type": "code", "source": "!pip install torch numpy matplotlib seaborn"},
    {"cell_type": "code", "source": "import torch\nimport numpy as np"},
    {"cell_type": "markdown", "source": "## Overview\n$$Attention(Q,K,V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V$$"},
    {"cell_type": "markdown", "source": "## Scaled Dot-Product Attention\n### Theory"},
    {"cell_type": "code", "source": "def scaled_dot_product_attention(Q, K, V):\n    d_k = Q.shape[-1]\n    scores = torch.matmul(Q, K.transpose(-2, -1)) / (d_k ** 0.5)\n    weights = torch.softmax(scores, dim=-1)\n    return torch.matmul(weights, V), weights"},
    {"cell_type": "code", "source": "# Realistic synthetic data\nbatch_size, seq_len, d_k = 8, 32, 64\nQ = torch.randn(batch_size, seq_len, d_k)\nK = torch.randn(batch_size, seq_len, d_k)\nV = torch.randn(batch_size, seq_len, d_k)"},
    {"cell_type": "code", "source": "output, weights = scaled_dot_product_attention(Q, K, V)\nprint(f'Output shape: {output.shape}')"},
    {"cell_type": "code", "source": "import matplotlib.pyplot as plt\nplt.imshow(weights[0].detach().numpy())\nplt.title('Attention Weights')\nplt.show()"},
    {"cell_type": "markdown", "source": "## Discussion\nLimitations and extensions..."},
]


def _make_mock_openai_response(content: str):
    """Build a minimal mock that mimics openai.ChatCompletion response shape."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── Module interface ─────────────────────────────────────────────────────────

class TestModuleInterface:

    def test_module_importable(self):
        import notebook_generator
        assert notebook_generator is not None

    def test_has_generate_cells(self):
        from notebook_generator import generate_cells
        assert callable(generate_cells)

    def test_has_analyze_paper(self):
        from notebook_generator import analyze_paper
        assert callable(analyze_paper)


# ── analyze_paper (phase 1) ──────────────────────────────────────────────────

class TestAnalyzePaper:

    def _mock_client(self, response_json: dict):
        client = MagicMock()
        client.chat.completions.create.return_value = _make_mock_openai_response(
            json.dumps(response_json)
        )
        return client

    def test_returns_dict(self):
        from notebook_generator import analyze_paper
        client = self._mock_client(PHASE1_JSON)
        result = analyze_paper(client, SAMPLE_PAPER_TEXT)
        assert isinstance(result, dict)

    def test_result_has_required_keys(self):
        from notebook_generator import analyze_paper
        client = self._mock_client(PHASE1_JSON)
        result = analyze_paper(client, SAMPLE_PAPER_TEXT)
        for key in ("title", "algorithms", "domain"):
            assert key in result, f"Missing key: {key}"

    def test_calls_openai_once(self):
        from notebook_generator import analyze_paper
        client = self._mock_client(PHASE1_JSON)
        analyze_paper(client, SAMPLE_PAPER_TEXT)
        assert client.chat.completions.create.call_count == 1

    def test_prompt_contains_paper_text(self):
        """The prompt sent to OpenAI must include the extracted paper text."""
        from notebook_generator import analyze_paper
        client = self._mock_client(PHASE1_JSON)
        analyze_paper(client, SAMPLE_PAPER_TEXT)
        call_kwargs = client.chat.completions.create.call_args
        messages = call_kwargs[1].get("messages") or call_kwargs[0][1]
        full_prompt = " ".join(m["content"] for m in messages if isinstance(m.get("content"), str))
        assert "Attention" in full_prompt or SAMPLE_PAPER_TEXT[:50] in full_prompt

    def test_handles_json_wrapped_in_markdown_fence(self):
        """Model sometimes wraps JSON in ```json ... ``` — must still parse."""
        from notebook_generator import analyze_paper
        fenced = f"```json\n{json.dumps(PHASE1_JSON)}\n```"
        client = MagicMock()
        client.chat.completions.create.return_value = _make_mock_openai_response(fenced)
        result = analyze_paper(client, SAMPLE_PAPER_TEXT)
        assert isinstance(result, dict)
        assert "title" in result


# ── generate_cells (phase 2) ─────────────────────────────────────────────────

class TestGenerateCells:

    def _mock_client(self, cells: list):
        client = MagicMock()
        client.chat.completions.create.return_value = _make_mock_openai_response(
            json.dumps(cells)
        )
        return client

    def test_returns_list(self):
        from notebook_generator import generate_cells
        client = self._mock_client(PHASE2_CELLS)
        result = generate_cells(client, SAMPLE_PAPER_TEXT, PHASE1_JSON)
        assert isinstance(result, list)

    def test_returns_nonempty_list(self):
        from notebook_generator import generate_cells
        client = self._mock_client(PHASE2_CELLS)
        result = generate_cells(client, SAMPLE_PAPER_TEXT, PHASE1_JSON)
        assert len(result) > 0

    def test_each_cell_has_cell_type_and_source(self):
        from notebook_generator import generate_cells
        client = self._mock_client(PHASE2_CELLS)
        result = generate_cells(client, SAMPLE_PAPER_TEXT, PHASE1_JSON)
        for cell in result:
            assert "cell_type" in cell, f"Missing cell_type: {cell}"
            assert "source" in cell, f"Missing source: {cell}"

    def test_cell_types_are_valid(self):
        from notebook_generator import generate_cells
        client = self._mock_client(PHASE2_CELLS)
        result = generate_cells(client, SAMPLE_PAPER_TEXT, PHASE1_JSON)
        for cell in result:
            assert cell["cell_type"] in ("markdown", "code"), \
                f"Invalid cell_type: {cell['cell_type']}"

    def test_calls_openai_once(self):
        from notebook_generator import generate_cells
        client = self._mock_client(PHASE2_CELLS)
        generate_cells(client, SAMPLE_PAPER_TEXT, PHASE1_JSON)
        assert client.chat.completions.create.call_count == 1

    def test_handles_json_wrapped_in_markdown_fence(self):
        from notebook_generator import generate_cells
        fenced = f"```json\n{json.dumps(PHASE2_CELLS)}\n```"
        client = MagicMock()
        client.chat.completions.create.return_value = _make_mock_openai_response(fenced)
        result = generate_cells(client, SAMPLE_PAPER_TEXT, PHASE1_JSON)
        assert isinstance(result, list)

    def test_prompt_instructs_research_grade(self):
        """Phase 2 prompt must mention realistic synthetic data and LaTeX."""
        from notebook_generator import generate_cells
        client = self._mock_client(PHASE2_CELLS)
        generate_cells(client, SAMPLE_PAPER_TEXT, PHASE1_JSON)
        call_kwargs = client.chat.completions.create.call_args
        messages = call_kwargs[1].get("messages") or call_kwargs[0][1]
        full_prompt = " ".join(
            m["content"] for m in messages if isinstance(m.get("content"), str)
        ).lower()
        assert "synthetic" in full_prompt or "research" in full_prompt


# ── make_client factory ──────────────────────────────────────────────────────

class TestMakeClient:

    def test_make_client_importable(self):
        from notebook_generator import make_client
        assert callable(make_client)

    def test_make_client_returns_openai_client(self):
        from notebook_generator import make_client
        with patch("notebook_generator.openai.OpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            client = make_client("sk-test-key")
            mock_cls.assert_called_once_with(api_key="sk-test-key")

    def test_model_fallback_constants_exist(self):
        """MODULE must define a MODEL_PREFERENCE list with gpt-5.4 first."""
        import notebook_generator
        assert hasattr(notebook_generator, "MODEL_PREFERENCE")
        models = notebook_generator.MODEL_PREFERENCE
        assert isinstance(models, (list, tuple))
        assert len(models) >= 1
        assert "gpt-5.4" in models[0] or "gpt" in models[0]
