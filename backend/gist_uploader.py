"""GitHub Gist upload — creates a public Gist and returns a Colab URL.

Usage:
    colab_url = upload_gist(nb_bytes, github_token)

The returned URL has the form:
    https://colab.research.google.com/gist/{username}/{gist_id}
"""
import httpx

_GIST_API = "https://api.github.com/gists"


def _build_colab_url(username: str, gist_id: str) -> str:
    return f"https://colab.research.google.com/gist/{username}/{gist_id}"


def upload_gist(nb_bytes: bytes, github_token: str) -> str:
    """Upload *nb_bytes* as a public GitHub Gist and return the Colab URL.

    Args:
        nb_bytes: Raw `.ipynb` file content.
        github_token: GitHub personal access token with the ``gist`` scope.

    Returns:
        Colab URL string.

    Raises:
        RuntimeError: If the GitHub API returns a non-2xx status code.
    """
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "description": "Paper2Notebook — generated Colab notebook",
        "public": True,
        "files": {
            "notebook.ipynb": {
                "content": nb_bytes.decode("utf-8"),
            }
        },
    }

    response = httpx.post(_GIST_API, headers=headers, json=payload, timeout=30)

    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"GitHub Gist API returned {response.status_code}: {response.text}"
        )

    data = response.json()
    gist_id = data["id"]
    username = data["owner"]["login"]
    return _build_colab_url(username, gist_id)
