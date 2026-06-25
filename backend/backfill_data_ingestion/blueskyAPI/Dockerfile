# Base image
FROM python:3.13-slim

# Install uv (for faster dependency install at build time only)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

# Set working directory
WORKDIR /code

# Copy dependency files first (better caching)
COPY pyproject.toml uv.lock ./

# Install dependencies INTO system Python (not a venv)
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy your script
COPY blueskyapi.py .

# Run the script directly (no uv run, no venv at runtime)
ENTRYPOINT ["python", "-u", "blueskyapi.py"]