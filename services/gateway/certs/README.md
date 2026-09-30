# TLS certificates

This directory is intentionally empty in version control. `docker-compose.yml` mounts it
into the nginx gateway at `/etc/nginx/certs`, and `nginx.conf` expects `server.crt` and
`server.key` to be present.

Generate a self-signed pair for local development before the first `docker compose up`:

```bash
openssl req -x509 -newkey rsa:4096 -nodes -days 365 \
  -keyout server.key -out server.crt \
  -subj "/CN=localhost"
```

Browsers will warn about the self-signed certificate on first visit to
`https://localhost` — that is expected for the prototype. Never commit `*.key` or
`*.crt`; both are covered by `.gitignore`.
