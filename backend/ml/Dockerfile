FROM python:3.11-slim

# Install uv (for faster dependency install at build time only)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

WORKDIR /app

# Copy dependency files first (better caching)
COPY pyproject.toml uv.lock ./

# Install dependencies INTO system Python (not a venv)
RUN uv pip install --system --no-cache -r pyproject.toml

COPY . .

# Run the script directly (no uv run, no venv at runtime)
ENTRYPOINT ["python", "-u", "updated_results.py", "--mode", "streaming"]