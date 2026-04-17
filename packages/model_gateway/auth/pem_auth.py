"""
PEM-based credential extraction for non-local model providers.

Three auth modes are supported, all loading credentials from a PEM/JSON file:

  google_service_account
    Reads a Google service-account JSON file (which contains the private key in
    PEM format).  Uses google-auth to sign a short-lived JWT and exchange it for
    an OAuth 2.0 access token.  Token is cached and refreshed automatically.

  azure_certificate
    Reads a PEM private key (+ optional PEM certificate) and uses it to sign a
    JWT client-assertion that is exchanged for an Azure AD bearer token via the
    client_credentials OAuth 2.0 flow.  Requires extra fields:
      tenant_id, client_id, scope (e.g. "https://cognitiveservices.azure.com/.default")

  jwt_bearer
    Signs a JWT directly with the PEM private key and returns it as the bearer
    token — no token-endpoint exchange.  Useful for Hugging Face enterprise,
    Databricks, or any API that accepts a self-signed JWT.  Requires extra fields:
      issuer, audience
    Optional extras:
      algorithm (default "RS256"), ttl_seconds (default 3600)

Token caching:
  Each credential caches its current token and only re-requests it when it is
  within TOKEN_REFRESH_MARGIN_SECONDS of expiry.  ``get_token()`` is safe to
  call on every API request without hitting the network most of the time.
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

TOKEN_REFRESH_MARGIN_SECONDS = 60  # refresh this many seconds before expiry


# ── Abstract base ─────────────────────────────────────────────────────────────


class PEMCredential(ABC):
    """
    Async credential that vends a short-lived bearer token from a PEM/JSON file.

    Subclasses implement ``_fetch_token()``; this base class handles caching
    and concurrent-refresh protection via an asyncio.Lock.
    """

    def __init__(self) -> None:
        self._token: str = ""
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        """Return a valid token, refreshing if it is expired or close to expiry."""
        if self._token and time.monotonic() < self._expires_at - TOKEN_REFRESH_MARGIN_SECONDS:
            return self._token
        async with self._lock:
            # Double-check after acquiring lock
            if self._token and time.monotonic() < self._expires_at - TOKEN_REFRESH_MARGIN_SECONDS:
                return self._token
            self._token, ttl = await self._fetch_token()
            self._expires_at = time.monotonic() + ttl
        return self._token

    @abstractmethod
    async def _fetch_token(self) -> tuple[str, float]:
        """
        Return (token_string, ttl_seconds).

        ttl_seconds is the number of seconds until the token expires.
        """


# ── Google Service Account ────────────────────────────────────────────────────


class GoogleServiceAccountCredential(PEMCredential):
    """
    Authenticates to Google APIs (Gemini, Vertex AI, etc.) using a service
    account JSON file.

    The service account JSON is the file you download from Google Cloud Console
    (IAM → Service Accounts → Keys → Add Key → JSON).  It contains the private
    key in PEM format.

    ``scopes`` defaults to the Google Generative AI scope; override for Vertex.
    """

    _DEFAULT_SCOPE = "https://www.googleapis.com/auth/generative-language"

    def __init__(self, sa_json_path: str, scopes: list[str] | None = None) -> None:
        super().__init__()
        self._sa_json_path = sa_json_path
        self._scopes = scopes or [self._DEFAULT_SCOPE]

    async def _fetch_token(self) -> tuple[str, float]:
        # google-auth is synchronous; run in executor to avoid blocking the loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_sync)

    def _fetch_sync(self) -> tuple[str, float]:
        from google.oauth2 import service_account
        import google.auth.transport.requests

        creds = service_account.Credentials.from_service_account_file(
            self._sa_json_path,
            scopes=self._scopes,
        )
        request = google.auth.transport.requests.Request()
        creds.refresh(request)

        token: str = creds.token
        # google-auth expiry is a datetime; convert to seconds-from-now TTL
        expiry = creds.expiry
        if expiry is not None:
            import datetime
            ttl = max(60.0, (expiry - datetime.datetime.utcnow()).total_seconds())
        else:
            ttl = 3600.0
        return token, ttl


# ── Azure Certificate ─────────────────────────────────────────────────────────


class AzureCertificateCredential(PEMCredential):
    """
    Authenticates to Azure OpenAI (or any Azure AD-protected resource) using a
    PEM certificate and private key via the OAuth 2.0 client_credentials flow
    with a JWT client assertion (RFC 7523).

    Required extra fields in models.yaml:
      tenant_id: "${AZURE_TENANT_ID}"
      client_id: "${AZURE_CLIENT_ID}"
      scope:     "https://cognitiveservices.azure.com/.default"

    ``pem_file`` may be a combined cert+key PEM, or just the private key.
    ``cert_file`` (optional) is the public certificate PEM for the x5t thumbprint.
    """

    def __init__(
        self,
        pem_file: str,
        tenant_id: str,
        client_id: str,
        scope: str,
        cert_file: str = "",
    ) -> None:
        super().__init__()
        self._pem_file = pem_file
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._scope = scope
        self._cert_file = cert_file

    async def _fetch_token(self) -> tuple[str, float]:
        import hashlib
        import base64
        import httpx

        private_key, x5t = self._load_key_and_thumbprint()

        now = int(time.time())
        payload = {
            "iss": self._client_id,
            "sub": self._client_id,
            "aud": f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token",
            "jti": _random_jti(),
            "nbf": now,
            "iat": now,
            "exp": now + 600,
        }
        headers: dict[str, Any] = {"alg": "RS256", "typ": "JWT"}
        if x5t:
            headers["x5t"] = x5t

        import jwt
        assertion = jwt.encode(payload, private_key, algorithm="RS256", headers=headers)

        token_url = (
            f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        )
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_assertion_type": (
                        "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
                    ),
                    "client_assertion": assertion,
                    "scope": self._scope,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        access_token: str = data["access_token"]
        ttl = float(data.get("expires_in", 3600))
        return access_token, ttl

    def _load_key_and_thumbprint(self) -> tuple[Any, str]:
        """Return (private_key_object, x5t_base64url) for the certificate."""
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from cryptography.x509 import load_pem_x509_certificate
        import base64
        import hashlib

        key_pem = Path(self._pem_file).read_bytes()
        private_key = load_pem_private_key(key_pem, password=None)

        x5t = ""
        cert_path = self._cert_file or self._pem_file
        try:
            cert_pem = Path(cert_path).read_bytes()
            cert = load_pem_x509_certificate(cert_pem)
            fingerprint = cert.fingerprint(__import__("cryptography.hazmat.primitives.hashes", fromlist=["SHA1"]).SHA1())
            x5t = base64.urlsafe_b64encode(fingerprint).rstrip(b"=").decode()
        except Exception:
            pass

        return private_key, x5t


# ── Generic JWT Bearer ────────────────────────────────────────────────────────


class JWTBearerCredential(PEMCredential):
    """
    Signs a JWT with a PEM private key and uses it directly as a Bearer token
    (no token-endpoint exchange).

    Useful for: Hugging Face Enterprise, Databricks, custom OIDC-protected APIs,
    or any service that validates JWT signatures rather than issuing their own tokens.

    Required extra fields in models.yaml:
      issuer:   your app / client id
      audience: the API resource you're calling

    Optional:
      algorithm:   RS256 (default) | ES256 | RS384 | RS512
      ttl_seconds: 3600 (default)
      claims:      arbitrary additional claims dict
    """

    def __init__(
        self,
        pem_file: str,
        issuer: str,
        audience: str,
        algorithm: str = "RS256",
        ttl_seconds: int = 3600,
        extra_claims: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._pem_file = pem_file
        self._issuer = issuer
        self._audience = audience
        self._algorithm = algorithm
        self._ttl_seconds = ttl_seconds
        self._extra_claims = extra_claims or {}

    async def _fetch_token(self) -> tuple[str, float]:
        import jwt

        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": self._issuer,
            "sub": self._issuer,
            "aud": self._audience,
            "iat": now,
            "nbf": now,
            "exp": now + self._ttl_seconds,
            "jti": _random_jti(),
            **self._extra_claims,
        }

        private_key = Path(self._pem_file).read_text(encoding="utf-8")
        token = jwt.encode(payload, private_key, algorithm=self._algorithm)
        return token, float(self._ttl_seconds)


# ── Factory ───────────────────────────────────────────────────────────────────


def build_pem_credential(
    pem_file: str,
    auth_mode: str,
    extra: dict[str, Any] | None = None,
) -> PEMCredential:
    """
    Build the right PEMCredential subclass from the provider config.

    Args:
        pem_file:  Absolute path to PEM private key, combined cert+key, or
                   Google service account JSON.
        auth_mode: One of ``google_service_account``, ``azure_certificate``,
                   ``jwt_bearer``.
        extra:     Provider-specific extra fields from ProviderConfig.extra.

    Raises:
        ValueError: if auth_mode is unknown or required extra keys are missing.
    """
    extra = extra or {}

    if auth_mode == "google_service_account":
        scopes_raw = extra.get("scopes", "")
        scopes = [s.strip() for s in scopes_raw.split(",")] if scopes_raw else None
        return GoogleServiceAccountCredential(
            sa_json_path=pem_file,
            scopes=scopes,
        )

    if auth_mode == "azure_certificate":
        _require_extra(extra, ["tenant_id", "client_id", "scope"], auth_mode)
        return AzureCertificateCredential(
            pem_file=pem_file,
            tenant_id=extra["tenant_id"],
            client_id=extra["client_id"],
            scope=extra["scope"],
            cert_file=extra.get("cert_file", ""),
        )

    if auth_mode == "jwt_bearer":
        _require_extra(extra, ["issuer", "audience"], auth_mode)
        return JWTBearerCredential(
            pem_file=pem_file,
            issuer=extra["issuer"],
            audience=extra["audience"],
            algorithm=extra.get("algorithm", "RS256"),
            ttl_seconds=int(extra.get("ttl_seconds", 3600)),
            extra_claims={
                k: v
                for k, v in extra.items()
                if k not in {"issuer", "audience", "algorithm", "ttl_seconds"}
            },
        )

    raise ValueError(
        f"Unknown auth_mode '{auth_mode}'. "
        "Supported: google_service_account, azure_certificate, jwt_bearer"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _require_extra(extra: dict, keys: list[str], auth_mode: str) -> None:
    missing = [k for k in keys if not extra.get(k)]
    if missing:
        raise ValueError(
            f"auth_mode '{auth_mode}' requires extra fields: {missing}. "
            "Add them under the provider's 'extra:' key in models.yaml."
        )


def _random_jti() -> str:
    import uuid
    return str(uuid.uuid4())
