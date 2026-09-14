# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=1

# System deps only when needed to compile wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

# Create virtual env once so layers cache on requirements changes
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

# Copy only dependency files first to leverage Docker layer caching
# If you use requirements.txt
COPY requirements.txt ./

# If you use pyproject.toml, uncomment the next two lines and comment out requirements.txt
# COPY pyproject.toml poetry.lock* ./
# RUN pip install --upgrade pip && pip install .  # assumes your package is buildable

# Install dependencies
RUN pip install --upgrade pip && \
    if [ -f "requirements.txt" ]; then pip install -r requirements.txt; fi

# Now copy the rest of your app
COPY . .

# Create a non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app /opt/venv
USER appuser

# Expose the common app port
EXPOSE 8000

# Default command for a simple script entry point
# Change this to match your app
# For example, if your entry point is app.py:
CMD ["python", "app.py"]

# If you are running FastAPI with Uvicorn, use this instead:
# CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

# Healthcheck (optional, useful for web apps)
# HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
#   CMD wget -qO- http://127.0.0.1:8000/health || exit 1
