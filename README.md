# Paper2Notebook

![Backend CI](https://github.com/senthilkumarkuppan/paper2notebook/actions/workflows/ci-backend.yml/badge.svg)

Convert a research paper PDF into a production-quality Google Colab notebook in one click.

Upload a PDF, enter your OpenAI API key, and receive a fully runnable `.ipynb` notebook with realistic synthetic data, rigorous algorithm implementations, LaTeX math commentary, and visualizations — powered by OpenAI's reasoning model.

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Python | 3.10+ |
| Node | 18+ |
| npm | 9+ |

---

## Installation

### 1. Clone the repo

```bash
git clone <repo-url>
cd skills_project
```

### 2. Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy the environment template:

```bash
cp ../.env.example ../.env
```

The `.env` file is optional — users enter their API key in the UI at runtime.

### 3. Frontend setup

```bash
cd ../frontend
npm install
```

---

## Running the app

Open two terminals.

**Terminal 1 — backend:**

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — frontend:**

```bash
cd frontend
npm run dev
```

Then open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Usage

1. **Gemini API Key** — paste your `AIza...` key into the API key field.
   Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
   The key is sent directly to Google from the backend and never stored.

2. **PDF upload** — drag-and-drop a research paper PDF onto the drop zone, or click to browse.

3. **Generate** — click **Generate Notebook**. A live progress panel shows each phase:
   - Parsing PDF
   - Analyzing paper (metadata + algorithms)
   - Generating implementation
   - Assembling notebook
   - *(optional)* Uploading to GitHub Gist

4. **Download** — the `.ipynb` file downloads automatically when generation completes.

---

## Open in Colab

To get a one-click **Open in Colab ↗** button after generation:

1. Create a GitHub Personal Access Token with the **`gist`** scope at
   `github.com → Settings → Developer settings → Personal access tokens`
2. Expand the **Optional — for Open in Colab** section in the UI and paste your token.

The backend uploads the notebook as a public GitHub Gist, then constructs the Colab URL:
`https://colab.research.google.com/gist/{username}/{gist_id}`

---

## Model and fallback

The backend attempts models in this order:

1. `gemini-2.5-pro` *(primary — Google's most capable reasoning model)*
2. `gemini-2.0-flash` *(fallback)*

If the primary model is unavailable or rate-limited, the system automatically retries with the next model in the fallback chain.

---

## Environment variables (`.env`)

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Optional server-side default key (users can override in the UI) |
| `GITHUB_TOKEN` | Optional server-side GitHub token (users can override in the UI) |
| `HOST` | Backend bind address (default `0.0.0.0`) |
| `PORT` | Backend port (default `8000`) |

Copy `.env.example` to `.env` and fill in values as needed.

---

## Running tests

**Backend:**

```bash
cd backend
source .venv/bin/activate
python3 -m pytest ../tests/ -v
```

**Frontend E2E:**

```bash
cd frontend
npm run test:e2e
```

---

## Docker (local stack)

Requires Docker and Docker Compose.

```bash
cp .env.example .env
# Add your GEMINI_API_KEY to .env

docker compose up
```

- Frontend: http://localhost
- Backend health: http://localhost/health

```bash
docker compose down   # stop and remove containers
```

---

## AWS Deployment (CI/CD)

The CD workflow (`.github/workflows/cd.yml`) builds and deploys on every push to `master`.

**Required GitHub repository secrets:**

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key |
| `AWS_REGION` | e.g. `us-east-1` |
| `AWS_ACCOUNT_ID` | 12-digit AWS account ID |

**Infrastructure setup (one-time, with Terraform):**

```bash
cd terraform
terraform init
terraform apply
```

**Store Gemini API key in SSM (one-time):**

```bash
aws ssm put-parameter \
  --name /paper2notebook/gemini_api_key \
  --value "AIza..." \
  --type SecureString
```
