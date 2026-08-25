FROM python:3.12.13-alpine3.23 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app
RUN apk upgrade --no-cache && \
    apk add --no-cache su-exec && \
    addgroup -S app && adduser -S -G app app && \
    mkdir -p \
      /var/lib/password-detective/desktop-plugins \
      /var/lib/password-detective/desktop-updates \
      /var/lib/password-detective/site-assets && \
    chown -R app:app /var/lib/password-detective
COPY apps/api/pyproject.toml ./
COPY apps/api/src ./src
COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY infra/docker/api-entrypoint.sh /usr/local/bin/password-detective-api-entrypoint
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 . && \
    sed -i 's/\r$//' /usr/local/bin/password-detective-api-entrypoint && \
    chmod 0755 /usr/local/bin/password-detective-api-entrypoint
ENTRYPOINT ["password-detective-api-entrypoint"]
EXPOSE 8000
CMD ["uvicorn", "password_detective.main:app", "--host", "0.0.0.0", "--port", "8000"]
