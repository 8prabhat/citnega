# Remote Worker Bootstrap And Rotation Playbook

Operational guide for provisioning remote worker secrets, enabling mTLS, rotating keys, and signing benchmark publications.

## 1. Bootstrap Secrets

Generate a fresh operator bundle:

```bash
citnega remote bootstrap-secrets \
  --signing-key-id 2026-04 \
  --include-benchmark-publication-key
```

JSON output is available for automation:

```bash
citnega remote bootstrap-secrets \
  --signing-key-id 2026-04 \
  --format json
```

Store the generated values in a secret manager or CI secret store. Do not commit the raw keys into `settings.toml`.

Required secrets:

- `CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY_ID`
- `CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY`
- `CITNEGA_REMOTE_AUTH_TOKEN`
- `CITNEGA_BENCHMARK_PUBLICATION_SIGNING_KEY_ID`
- `CITNEGA_BENCHMARK_PUBLICATION_SIGNING_KEY`

## 2. First Remote Worker Bring-Up

Minimum worker configuration:

```toml
[remote]
allowed_callables = ["qa_agent", "release_agent", "security_agent"]
service_isolation_profile = "process"
envelope_signing_key_id = "2026-04"
envelope_verification_keys = []
```

Recommended environment:

```bash
export CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY_ID='2026-04'
export CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY='...'
export CITNEGA_REMOTE_AUTH_TOKEN='...'
```

Start the worker:

```bash
citnega remote serve \
  --allow-callable qa_agent \
  --allow-callable release_agent \
  --allow-callable security_agent
```

Validation:

- `GET /health` reports `active_signing_key_id`
- `accepted_key_ids` contains the active key id
- `tls_enabled` and `mtls_required` reflect the deployed transport mode

## 3. Enabling HTTPS And mTLS

Server-side configuration:

```toml
[remote]
service_tls_cert_path = "/etc/citnega/tls/server-cert.pem"
service_tls_key_path = "/etc/citnega/tls/server-key.pem"
service_tls_client_ca_path = "/etc/citnega/tls/clients-ca.pem"
service_tls_require_client_cert = true
```

Client/orchestrator configuration:

```toml
[remote]
worker_mode = "http"
http_endpoint = "https://worker.example.com:8787/invoke"
verify_tls = true
ca_cert_path = "/etc/citnega/tls/worker-ca.pem"
client_cert_path = "/etc/citnega/tls/client-cert.pem"
client_key_path = "/etc/citnega/tls/client-key.pem"
```

Operational notes:

- keep bearer auth enabled even when mTLS is active
- issue worker server certificates with `localhost` and worker DNS SANs when applicable
- issue dedicated client certificates per orchestrator lane or environment
- if the worker runs with `service_isolation_profile="container"`, pass the TLS files through `citnega remote serve`; the built-in launcher mounts and forwards them automatically

## 4. Rotating Envelope Signing Keys

Target state:

- new dispatches are signed with the new key id
- workers continue to accept the previous key during the drain window

Rotation sequence:

1. Generate a new bundle:
   `citnega remote bootstrap-secrets --signing-key-id 2026-05`
2. Update workers first:
   - `CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY_ID=2026-05`
   - `CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY=<new-secret>`
   - `envelope_verification_keys = ["2026-04=<old-secret>", "2026-05=<new-secret>"]`
3. Confirm `/health` returns:
   - `active_signing_key_id = "2026-05"`
   - `accepted_key_ids = ["2026-04", "2026-05"]`
4. Update orchestrators/clients to sign with `2026-05`.
5. Observe at least one successful benchmark or soak window with no `unknown_key_id` or `signature_mismatch` failures.
6. Remove the old verification key after the drain period:
   - `envelope_verification_keys = ["2026-05=<new-secret>"]`

Rollback:

- revert clients to the previous key id
- restore the old worker signing key id and verification set
- keep both keys accepted until traffic stabilizes

## 5. Rotating Client Certificates

1. Publish the new client CA bundle or intermediate trust chain to workers.
2. Issue new client certificates to orchestrators.
3. Restart or reload clients with:
   - `ca_cert_path`
   - `client_cert_path`
   - `client_key_path`
4. Verify mTLS traffic succeeds.
5. Remove the old CA bundle from workers after the overlap window.

## 6. Signed Benchmark Publication

Benchmark publication is signed separately from remote dispatch:

```bash
export CITNEGA_BENCHMARK_PUBLICATION_SIGNING_KEY_ID='benchmark-2026-04'
export CITNEGA_BENCHMARK_PUBLICATION_SIGNING_KEY='...'
export CITNEGA_BENCHMARK_PUBLICATION_REQUIRE_SIGNATURE='true'
```

Running:

```bash
.venv/bin/python scripts/run_benchmark_matrix.py
```

Artifacts:

- `docs/evidence/benchmark_matrix_latest.json`
- `docs/evidence/benchmark_matrix_history.jsonl`
- `docs/evidence/benchmark_publication_latest.json`
- `docs/evidence/benchmark_publication_history.jsonl`

`benchmark_publication_latest.json` signs:

- benchmark report digest
- history digest
- branch metadata
- CI run metadata
- lane trend summary

This is the artifact intended for longitudinal dashboard ingestion.

## 7. Incident Checks

If remote traffic fails after a change, inspect in this order:

1. `/health` for `active_signing_key_id`, `accepted_key_ids`, `tls_enabled`, `mtls_required`
2. orchestrator remote settings:
   - `http_endpoint`
   - `verify_tls`
   - `ca_cert_path`
   - `client_cert_path`
   - `client_key_path`
3. worker certificate/key and client CA files
4. `Authorization` bearer token
5. benchmark publication signature env vars in CI if dashboard artifacts stopped updating
