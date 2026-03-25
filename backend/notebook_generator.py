"""Two-phase OpenAI notebook generation.

Phase 1 — analyze_paper(): extract structured metadata from the paper text.
Phase 2 — generate_cells(): produce the full notebook cell JSON array.
"""
import json
import re
from typing import Any

import openai

# Model preference order: try gpt-5.4 first, fall back if unavailable.
MODEL_PREFERENCE: list[str] = ["gpt-5.4", "o3", "gpt-4.1"]

# ── Prompts ──────────────────────────────────────────────────────────────────

_PHASE1_SYSTEM = """\
You are a world-class research scientist and ML engineer. Your task is to analyse \
a research paper and extract structured metadata that will be used to generate \
a production-quality Google Colab tutorial notebook.

Respond ONLY with a valid JSON object — no markdown fences, no commentary.\
"""

_PHASE1_USER = """\
Analyse the following research paper text and return a JSON object with EXACTLY these keys:
{{
  "title": "Full paper title",
  "authors": ["Author 1", "Author 2"],
  "venue": "Conference or journal name and year",
  "domain": "Research domain (e.g. Natural Language Processing / Transformers)",
  "algorithms": [
    {{
      "name": "Algorithm name",
      "description": "One-sentence description of what it does"
    }}
  ],
  "key_equations": [
    "LaTeX string for equation 1",
    "LaTeX string for equation 2"
  ],
  "datasets_mentioned": ["dataset 1", "dataset 2"],
  "dependencies": ["torch", "numpy", "matplotlib"]
}}

The algorithms list should contain ALL significant algorithms, methods, and \
architectures described in the paper (typically 2-5).

PAPER TEXT:
---
{paper_text}
---\
"""

_PHASE2_SYSTEM = """\
You are a world-class ML researcher and engineer writing a PRODUCTION-QUALITY \
Google Colab tutorial notebook for top researchers at companies like OpenAI and DeepMind.

YOUR NOTEBOOK MUST:
1. Be completely self-contained and runnable in Google Colab
2. Use REALISTIC synthetic data that mirrors the actual problem domain — \
   NOT toy examples like iris or MNIST. Generate synthetic data that reflects \
   the statistical properties and structure of real data for this domain.
3. Implement the core algorithms in full Python — NOT pseudocode. Include:
   - Proper type hints
   - Docstrings with Args/Returns sections
   - Error handling
   - Clear variable names
4. Write ALL mathematical formulas in LaTeX inside markdown cells using $$ or $
5. Include matplotlib/seaborn visualizations of results
6. Compare against at least one baseline method
7. Target Python 3.10+, PyTorch preferred for neural methods, numpy/scipy otherwise

CELL FORMAT: Respond ONLY with a JSON array of cell objects. Each cell:
  {"cell_type": "markdown" | "code", "source": "cell content as string"}

DO NOT wrap the JSON in markdown fences.\
"""

_PHASE2_USER = """\
Generate a research-grade Google Colab tutorial notebook implementing the \
algorithms from this paper.

PAPER METADATA:
{metadata_json}

PAPER TEXT (for implementation reference):
---
{paper_text}
---

REQUIRED NOTEBOOK STRUCTURE (produce ALL of these sections):
1. Title cell — paper title, authors, venue, one-paragraph abstract
2. Setup cell — !pip install all required packages (with version pins where possible)
3. Imports cell — all imports, seeded random state for reproducibility
4. Overview cell — paper's core contribution, key equations in LaTeX, intuition
5. For EACH algorithm in the metadata:
   a. Theory cell (markdown) — full math formulation in LaTeX, assumptions, time/space complexity
   b. Implementation cell (code) — complete Python class/function, type-hinted, docstrings
   c. Synthetic data cell (code) — generate REALISTIC synthetic data for this domain
   d. Experiment cell (code) — run algorithm, measure metrics (loss, accuracy, time, etc.)
   e. Visualisation cell (code) — matplotlib/seaborn plots of results
6. Comparison cell (code) — compare to a baseline; table of results
7. Discussion cell (markdown) — limitations, extensions, connection to related work

Produce a thorough, publication-quality notebook. This will be used by ML researchers \
to understand and replicate the paper.\
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` fences if present."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _call_with_fallback(
    client: openai.OpenAI,
    messages: list[dict],
    response_format: str = "text",
) -> str:
    """Try MODEL_PREFERENCE in order; return the content string of the first success."""
    last_exc: Exception | None = None
    for model in MODEL_PREFERENCE:
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_completion_tokens": 16000,
            }
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
    raise RuntimeError(
        f"All models in MODEL_PREFERENCE failed. Last error: {last_exc}"
    ) from last_exc


# ── Public API ────────────────────────────────────────────────────────────────

def make_client(api_key: str) -> openai.OpenAI:
    """Create and return an OpenAI client authenticated with *api_key*."""
    return openai.OpenAI(api_key=api_key)


def analyze_paper(client: openai.OpenAI, paper_text: str) -> dict[str, Any]:
    """Phase 1: extract structured metadata from raw paper text.

    Args:
        client: Authenticated OpenAI client.
        paper_text: Full extracted text of the research paper.

    Returns:
        dict with keys: title, authors, venue, domain, algorithms,
        key_equations, datasets_mentioned, dependencies.
    """
    messages = [
        {"role": "system", "content": _PHASE1_SYSTEM},
        {
            "role": "user",
            "content": _PHASE1_USER.format(paper_text=paper_text[:120_000]),
        },
    ]
    raw = _call_with_fallback(client, messages)
    cleaned = _strip_json_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Phase 1 model returned invalid JSON: {exc}\n\nRaw:\n{raw}") from exc


def generate_cells(
    client: openai.OpenAI,
    paper_text: str,
    metadata: dict[str, Any],
) -> list[dict[str, str]]:
    """Phase 2: generate the full notebook cell JSON array.

    Args:
        client: Authenticated OpenAI client.
        paper_text: Full extracted text of the research paper.
        metadata: Structured metadata dict from analyze_paper().

    Returns:
        List of cell dicts, each with 'cell_type' and 'source' keys.
    """
    messages = [
        {"role": "system", "content": _PHASE2_SYSTEM},
        {
            "role": "user",
            "content": _PHASE2_USER.format(
                metadata_json=json.dumps(metadata, indent=2),
                paper_text=paper_text[:80_000],
            ),
        },
    ]
    raw = _call_with_fallback(client, messages)
    cleaned = _strip_json_fences(raw)
    try:
        cells = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Phase 2 model returned invalid JSON: {exc}\n\nRaw:\n{raw}") from exc

    if not isinstance(cells, list):
        raise ValueError(f"Phase 2 expected a JSON array, got {type(cells).__name__}")

    # Validate and normalise each cell
    validated: list[dict[str, str]] = []
    for i, cell in enumerate(cells):
        if not isinstance(cell, dict):
            continue
        cell_type = cell.get("cell_type", "code")
        if cell_type not in ("markdown", "code"):
            cell_type = "code"
        source = cell.get("source", "")
        if not isinstance(source, str):
            source = str(source)
        validated.append({"cell_type": cell_type, "source": source})

    return validated
