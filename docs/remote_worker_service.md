# Remote Worker Service

Reference HTTP worker for Citnega remote orchestration.

## Purpose

The reference worker provides a concrete process boundary for `execution_target="remote"` steps.
It verifies signed run envelopes, enforces an explicit callable allowlist, and returns
standard `InvokeResult` payloads over HTTP.

## Start the Service

```bash
citnega remote serve \
  --allow-callable qa_agent \
  --allow-callable release_agent \
  --allow-callable security_agent
```

Defaults come from `[remote]` in `settings.toml`:

- `service_host`
- `service_port`
- `service_isolation_profile`
- `service_container_runtime`
- `service_container_image`
- `service_container_name`
- `allowed_callables`
- `envelope_signing_key`
- `envelope_signing_key_id`
- `envelope_verification_keys`
- `auth_token`
- `service_tls_cert_path`
- `service_tls_key_path`
- `service_tls_client_ca_path`
- `service_tls_require_client_cert`

## Endpoints

- `GET /health`
  Returns worker id, isolation profile, allowlist, auth/signature requirements, and TLS/mTLS state.
- `POST /invoke`
  Accepts the signed remote envelope, callable name, input payload, and session identifiers.

## Safety Controls

- Server-side allowlist is mandatory. The worker refuses to start without one.
- Payload hash is checked against the envelope before invocation.
- HMAC signature verification is enforced when signed envelopes are enabled.
- Rotated verification keys are supported using `envelope_signing_key_id` and
  `envelope_verification_keys` so old envelopes remain valid during key rollovers.
- Optional HTTPS is enabled with `service_tls_cert_path` and `service_tls_key_path`.
- Optional mTLS is enabled with `service_tls_client_ca_path` and
  `service_tls_require_client_cert = true`.
- `service_isolation_profile` controls whether the worker runs as a dedicated process
  or through the built-in Docker/Podman container launcher.

## Container Mode

When `service_isolation_profile="container"`, `citnega remote serve` launches a real
containerized worker and then re-enters the same CLI command inside the container.

Requirements:

- `service_container_runtime`: `docker` or `podman`
- `service_container_image`: image containing Citnega and Python
- current workspace mounted at `/workspace`
- app home mounted at `/citnega-app`
- explicit DB mount when `--db-path` is supplied

The host command remains the operator entrypoint; the containerized worker preserves
the same allowlist, auth token, envelope signing key id, accepted verification keys,
and TLS/mTLS file mappings.

## Bootstrap And Rotation

Generate a fresh operator bundle:

```bash
citnega remote bootstrap-secrets --signing-key-id 2026-04
```

Operational rotation and mTLS rollout guidance lives in:

- `docs/remote_worker_key_rotation_playbook.md`
