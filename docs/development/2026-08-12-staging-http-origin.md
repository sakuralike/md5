# Staging HTTP origin override

The staging server may be accessed directly over HTTP while TLS is not configured. Use `STAGING_CORS_ORIGINS` to provide the exact browser origins exposed by the staging web and admin ports; the default remains localhost for local Compose usage.

```powershell
$env:STAGING_CORS_ORIGINS = "http://111.229.195.138:5173,http://111.229.195.138:5174"
docker compose -f docker-compose.yml -f infra/staging/docker-compose.staging.api-ha.yml -f infra/staging/docker-compose.staging.http-origin.yml up -d api worker scheduler
```

This override is limited to CORS/origin validation and does not weaken authentication or allow wildcard origins.
