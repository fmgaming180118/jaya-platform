# Security

Do not report vulnerabilities in public issues. Send a minimal report to the
repository owner through the private contact channel configured for the release.
Do not include credentials, personal data, proprietary documents, or live
exploit payloads in the report.

## Deployment requirements

- Keep `.env`, provider keys, databases, uploaded documents, logs, and model
  files outside Git.
- Use a unique `JAYA_SECRET_KEY` and `JAYA_CORE_VAULT_PASSWORD` per deployment.
- Bind local development services to loopback unless an authenticated reverse
  proxy is configured.
- Restrict upload size, MIME type, path, and storage location.
- Disable optional autonomous capabilities by default.
- Review cloud-provider data handling before sending documents or prompts off
  device.

The project is public proprietary software. Public visibility does not grant
permission to use or deploy it; see `LICENSE`.
