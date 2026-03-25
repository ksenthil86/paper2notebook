"""Assemble a .ipynb notebook from a list of cell dicts using nbformat."""
import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

_DEFAULT_PIP_CELL = "!pip install numpy scipy matplotlib seaborn pandas torch"

_NOTEBOOK_METADATA = {
    "kernelspec": {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    },
    "language_info": {
        "name": "python",
        "version": "3.10.0",
    },
    "colab": {
        "provenance": [],
        "toc_visible": True,
    },
}


def build_notebook(cells: list[dict[str, str]]) -> bytes:
    """Convert a list of cell dicts into a valid .ipynb file as bytes.

    Args:
        cells: List of dicts with 'cell_type' ('markdown'|'code') and 'source'.

    Returns:
        UTF-8 encoded bytes of the nbformat v4 notebook JSON.
    """
    nb_cells = []

    # Determine whether a pip install cell already exists
    has_pip = any(
        c.get("cell_type") == "code" and c.get("source", "").strip().startswith("!pip install")
        for c in cells
    )

    pip_injected = False
    for cell in cells:
        cell_type = cell.get("cell_type", "code")
        source = cell.get("source", "")

        if cell_type == "markdown":
            nb_cells.append(new_markdown_cell(source))
        else:
            # Inject default pip cell before the first code cell if none present
            if not has_pip and not pip_injected:
                nb_cells.append(new_code_cell(_DEFAULT_PIP_CELL))
                pip_injected = True
            nb_cells.append(new_code_cell(source))

    # If still no pip cell (e.g. empty input or only markdown), inject one
    if not pip_injected and not has_pip:
        nb_cells.insert(0, new_code_cell(_DEFAULT_PIP_CELL))

    nb = new_notebook(cells=nb_cells, metadata=_NOTEBOOK_METADATA)
    nb.nbformat = 4
    nb.nbformat_minor = 5

    return nbformat.writes(nb).encode("utf-8")
