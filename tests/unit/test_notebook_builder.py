"""Task 5 — Unit tests: .ipynb assembly with nbformat."""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest
import nbformat


SAMPLE_CELLS = [
    {"cell_type": "markdown", "source": "# Attention Is All You Need\n## Tutorial Notebook"},
    {"cell_type": "code", "source": "!pip install torch==2.0.0 numpy matplotlib seaborn"},
    {"cell_type": "code", "source": "import torch\nimport numpy as np\nimport matplotlib.pyplot as plt"},
    {"cell_type": "markdown", "source": "## Overview\n$$Attention(Q,K,V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V$$"},
    {"cell_type": "code", "source": "def scaled_dot_product_attention(Q, K, V):\n    d_k = Q.shape[-1]\n    scores = (Q @ K.transpose(-2, -1)) / (d_k ** 0.5)\n    weights = torch.softmax(scores, dim=-1)\n    return weights @ V"},
]

CELLS_WITHOUT_PIP = [
    {"cell_type": "markdown", "source": "# My Paper"},
    {"cell_type": "code", "source": "x = 1 + 1"},
]


class TestBuildNotebook:

    def test_module_importable(self):
        import notebook_builder
        assert notebook_builder is not None

    def test_has_build_notebook(self):
        from notebook_builder import build_notebook
        assert callable(build_notebook)

    def test_returns_bytes(self):
        from notebook_builder import build_notebook
        result = build_notebook(SAMPLE_CELLS)
        assert isinstance(result, bytes)

    def test_output_is_valid_json(self):
        from notebook_builder import build_notebook
        result = build_notebook(SAMPLE_CELLS)
        nb = json.loads(result)
        assert isinstance(nb, dict)

    def test_nbformat_validates(self):
        """nbformat.validate() must pass without raising ValidationError."""
        from notebook_builder import build_notebook
        result = build_notebook(SAMPLE_CELLS)
        nb = nbformat.reads(result.decode(), as_version=4)
        nbformat.validate(nb)  # raises if invalid

    def test_notebook_version_is_4(self):
        from notebook_builder import build_notebook
        result = build_notebook(SAMPLE_CELLS)
        nb = json.loads(result)
        assert nb["nbformat"] == 4

    def test_kernel_is_python3(self):
        """Kernel spec must be python3 for Colab compatibility."""
        from notebook_builder import build_notebook
        result = build_notebook(SAMPLE_CELLS)
        nb = json.loads(result)
        ks = nb.get("metadata", {}).get("kernelspec", {})
        assert ks.get("name") == "python3"
        assert "Python 3" in ks.get("display_name", "")

    def test_cell_count_matches(self):
        """Number of cells in output equals number of input cells."""
        from notebook_builder import build_notebook
        result = build_notebook(SAMPLE_CELLS)
        nb = nbformat.reads(result.decode(), as_version=4)
        assert len(nb.cells) == len(SAMPLE_CELLS)

    def test_markdown_cells_preserved(self):
        from notebook_builder import build_notebook
        result = build_notebook(SAMPLE_CELLS)
        nb = nbformat.reads(result.decode(), as_version=4)
        markdown_cells = [c for c in nb.cells if c.cell_type == "markdown"]
        assert len(markdown_cells) == 2

    def test_code_cells_preserved(self):
        from notebook_builder import build_notebook
        result = build_notebook(SAMPLE_CELLS)
        nb = nbformat.reads(result.decode(), as_version=4)
        code_cells = [c for c in nb.cells if c.cell_type == "code"]
        assert len(code_cells) == 3

    def test_cell_source_preserved(self):
        """Source content of each cell must be preserved exactly."""
        from notebook_builder import build_notebook
        result = build_notebook(SAMPLE_CELLS)
        nb = nbformat.reads(result.decode(), as_version=4)
        for i, (original, built) in enumerate(zip(SAMPLE_CELLS, nb.cells)):
            assert built.source == original["source"], f"Cell {i} source mismatch"

    def test_pip_install_cell_is_first_code_cell(self):
        """When cells already have a pip install cell, it must be the first code cell."""
        from notebook_builder import build_notebook
        result = build_notebook(SAMPLE_CELLS)
        nb = nbformat.reads(result.decode(), as_version=4)
        code_cells = [c for c in nb.cells if c.cell_type == "code"]
        assert code_cells[0].source.startswith("!pip install")

    def test_injects_pip_cell_when_missing(self):
        """If no pip install cell present, builder injects one as first code cell."""
        from notebook_builder import build_notebook
        result = build_notebook(CELLS_WITHOUT_PIP)
        nb = nbformat.reads(result.decode(), as_version=4)
        code_cells = [c for c in nb.cells if c.cell_type == "code"]
        assert len(code_cells) >= 1
        assert "!pip install" in code_cells[0].source

    def test_handles_empty_cells_list(self):
        """Empty input produces a valid notebook with at least the pip install cell."""
        from notebook_builder import build_notebook
        result = build_notebook([])
        nb = nbformat.reads(result.decode(), as_version=4)
        nbformat.validate(nb)

    def test_colab_metadata_present(self):
        """Notebook metadata should include colab compatibility marker."""
        from notebook_builder import build_notebook
        result = build_notebook(SAMPLE_CELLS)
        nb = json.loads(result)
        metadata = nb.get("metadata", {})
        # Colab uses "colab" key or language_info python
        lang = metadata.get("language_info", {}).get("name", "")
        assert lang == "python"
