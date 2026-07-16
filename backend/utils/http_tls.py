import os


def get_httpx_verify() -> bool | str:
    """Return strict TLS verify setting for HTTPX clients.

    - Uses HTTPX default certificate validation when HTTPX_CA_BUNDLE is unset.
    - Uses the provided CA bundle path when HTTPX_CA_BUNDLE is set.
    """
    ca_bundle = str(os.environ.get("HTTPX_CA_BUNDLE") or "").strip()
    return ca_bundle if ca_bundle else True
