# syntax=docker/dockerfile:1

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /srv

RUN useradd --system --uid 10001 --home /srv appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# Verification image: adds tests, smoke scripts and dev dependencies.
FROM runtime AS verify
USER root
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY pyproject.toml ./
COPY tests ./tests
COPY scripts ./scripts
RUN chown -R appuser:appuser /srv
USER appuser
ENV APP_BASE_URL=http://app:8000
CMD ["python", "scripts/verify.py"]
