FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app && \
    mkdir -p /var/lib/password-detective/desktop-updates && \
    chown -R app:app /var/lib/password-detective
COPY apps/api/pyproject.toml ./
COPY apps/api/src ./src
COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 .
USER app
EXPOSE 8000
CMD ["uvicorn", "password_detective.main:app", "--host", "0.0.0.0", "--port", "8000"]
