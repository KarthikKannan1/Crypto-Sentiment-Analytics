# Dockerfile 
# Base image 
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

# 1. set up the working directory inside the container
WORKDIR /code

# 2. Copy only the dependency files first (better for caching)
COPY pyproject.toml uv.lock ./

# 3. set up our image by installing prerequisites
RUN uv pip install --system --no-cache -r pyproject.toml

COPY mastodonapi.py .

# 5. define what to do first when the container runs
ENTRYPOINT ["python", "-u", "mastodonapi.py"]