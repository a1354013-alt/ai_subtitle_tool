# Security Policy

## Overview

This document outlines the security measures implemented in the AI Video Subtitle Tool to protect against common vulnerabilities and ensure safe operation.

## File Upload Security

### Validation Layers

1. **Client-Side Validation**
   - Maximum file size: 2GB (enforced in `UploadForm.vue`)
   - Accepted extensions: `.mp4`, `.mkv`, `.avi`, `.mov`
   - Immediate feedback to users before upload

2. **Server-Side Validation**
   - MIME type verification via `ffprobe`
   - Actual media format validation (not just extension)
   - Maximum size enforcement at FastAPI level
   - Path traversal protection using `Path().resolve()` checks

### Path Traversal Protection

All file operations use absolute path resolution with explicit containment checks:

```python
# Example from backend/main.py (containment via Path.relative_to)
resolved_path = Path(filepath).resolve()
resolved_root = Path(allowed_root).resolve()
try:
    resolved_path.relative_to(resolved_root)
except ValueError:
    raise HTTPException(status_code=400, detail="Path traversal detected")
```

## CORS Configuration

### Default Policy
- **Development (recommended)**: explicit origin (`http://localhost:5173`) with credentials enabled
- **Alternative dev**: wildcard (`*`) only when credentials are disabled
- **Production**: explicit origin whitelist required when using credentials

### Environment Variables
```bash
CORS_ALLOWED_ORIGINS=https://example.com,https://api.example.com
CORS_ALLOW_CREDENTIALS=false  # Must be false when using wildcard
```

### Security Notes
- Wildcard (`*`) with credentials is explicitly forbidden (fail-fast)
- Credentials support requires explicit origin list
- All methods and headers allowed by default (customize as needed)

## API Security

### Authentication
Local demo defaults keep API authentication disabled. When `REQUIRE_AUTH_TOKEN=true`, middleware enforces token authentication for non-health API routes. For production deployment:

1. **Recommended**: Set `REQUIRE_AUTH_TOKEN=true` and a strong `AUTH_TOKEN`
2. **Alternative**: Deploy behind reverse proxy with authentication
3. **Frontend**: If you choose the built-in SPA token mode, `VITE_API_TOKEN` makes fetch requests include `X-API-Token`. It is embedded in the browser bundle and is not a protected server secret.

### Rate Limiting
`RATE_LIMIT_PER_IP` is enforced by middleware for non-health API routes as a per-IP hourly limit. Set it to `0` to disable for local development, and use a positive integer for production. Consider reverse-proxy or Redis-based limiting for distributed deployments.

## Environment Variables

### Sensitive Data
The following environment variables contain sensitive data:

| Variable | Purpose | Security Note |
|----------|---------|---------------|
| `OPENAI_API_KEY` | OpenAI API access | Never commit to version control |
| `REDIS_URL` | Redis connection | Use authentication in production |
| `CORS_ALLOWED_ORIGINS` | CORS policy | Configure per environment |
| `AUTH_TOKEN` | API token auth | Required when `REQUIRE_AUTH_TOKEN=true` |
| `VITE_API_TOKEN` | Optional frontend API token header | Public browser-bundle value; do not treat as a server secret |

`OPENAI_API_KEY` is optional for transcription-only usage and required when translation is requested. Missing OpenAI configuration should be treated as a translation feature warning, not as a general service startup failure.

When `REQUIRE_AUTH_TOKEN=true`, non-health API routes require either `Authorization: Bearer <token>` or `X-API-Token: <token>`. `/healthz`, `/readyz`, `/api/docs`, `/api/redoc`, and `/openapi.json` are excluded for diagnostics and documentation. Direct browser downloads use short-lived signed download tickets issued by authenticated requests to `/download-ticket`; permanent `AUTH_TOKEN` values are not placed in download URLs.

`STORAGE_BACKEND` controls storage selection explicitly. `STORAGE_BACKEND=local` always uses local storage. `STORAGE_BACKEND=s3` requires `S3_BUCKET` and optional dependencies from `requirements.optional-s3.txt`; S3 remains experimental unless manifest, subtitle download, batch download, cleanup, and rebuild behavior have all been verified for that deployment.

### Best Practices
1. Use `.env` files excluded from git (`.gitignore` includes `.env*`)
2. Use secrets management in production (Docker secrets, Kubernetes secrets, etc.)
3. Rotate API keys regularly
4. Use different keys for development and production

## Task Isolation

### File System
- Each task operates in isolated directory structure
- Temporary files cleaned up after task completion
- Atomic writes prevent partial file corruption

### Process Isolation
- Celery workers run as separate processes
- Task timeouts prevent runaway processes
- Memory limits via Celery configuration

## Dependencies

### Security Scanning
Regularly scan dependencies for vulnerabilities:

```bash
# Python
pip-audit -r requirements.txt

# Node.js
npm audit --omit=dev --audit-level=moderate
```

Current frontend audit status:

- Production audit must pass with 0 vulnerabilities.
- The recent production audit cleanup updated the `form-data` / `hasown` dependency chain.
- Production audit uses `npm audit --omit=dev --audit-level=moderate`. Full dev audit advisories are tracked separately.
- Runtime impact is limited because the reported issue targets the Vite development server, not the production build output.
- Recommended follow-up: schedule a dedicated compatibility pass to upgrade `vite`, `@vitejs/plugin-vue`, and `vitest` together, then re-run frontend lint/typecheck/test/build and CI on Node 20.

### Current Dependencies
- Backend: FastAPI, Celery, OpenAI, faster-whisper
- Frontend: Vue 3, TypeScript, Pinia

## Deployment Security

### Docker Security
1. Run containers as non-root user
2. Use minimal base images
3. Scan images for vulnerabilities
4. Keep images updated

### Network Security
1. Use HTTPS in production
2. Restrict Redis access to internal network
3. Use firewall rules to limit exposure
4. Consider deploying behind reverse proxy

## Monitoring & Logging

### Security Events to Monitor
- Failed upload attempts
- Path traversal attempts
- CORS violations
- API authentication failures when `REQUIRE_AUTH_TOKEN=true`
- Unusual task patterns

### Log Security
- Avoid logging sensitive data (API keys, tokens)
- Use structured logging for easier analysis
- Implement log rotation to prevent disk exhaustion

## Incident Response

### If Security Vulnerability Discovered
1. Document the issue
2. Assess impact scope
3. Apply fix or workaround
4. Notify affected users if necessary
5. Review and update security policies

## Future Enhancements

Consider implementing:
- [ ] API key authentication
- [ ] Rate limiting
- [ ] File content scanning (antivirus)
- [ ] Audit logging
- [ ] Automated security scanning in CI/CD
- [ ] Content Security Policy (CSP) headers
- [ ] HTTPS enforcement middleware

## Contact

For security concerns, please open an issue or contact the maintainers directly.
