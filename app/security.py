from __future__ import annotations

import hashlib
import hmac


def hash_purchase_token(token: str, pepper: str) -> str:
    return hmac.new(pepper.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_client_key(presented_key: str, configured_value: str) -> bool:
    value = configured_value.strip()
    if value.startswith("sha256:"):
        expected_hash = value[len("sha256:") :].strip().lower()
        actual_hash = hashlib.sha256(presented_key.encode("utf-8")).hexdigest()
        return hmac.compare_digest(actual_hash, expected_hash)
    if value.startswith("plain:"):
        expected_plain = value[len("plain:") :]
        return hmac.compare_digest(presented_key, expected_plain)
    # Backward compatibility for old plain values.
    return hmac.compare_digest(presented_key, value)
