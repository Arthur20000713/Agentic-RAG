FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN addgroup --system --gid 10001 livestock \
    && adduser --system --uid 10001 --ingroup livestock --home /opt/livestock livestock

WORKDIR /opt/livestock/app
COPY pyproject.toml ./
COPY backend ./backend
COPY config/settings.compose.yaml ./config/settings.compose.yaml
COPY tests/fixtures/rag_server ./tests/fixtures/rag_server
RUN pip install --no-cache-dir .
RUN mkdir -p /var/lib/livestock-ai \
    && chown -R livestock:livestock /var/lib/livestock-ai /opt/livestock

USER livestock
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
