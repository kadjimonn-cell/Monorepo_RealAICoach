"""Correlator utilities for threading applicant email replies back onto the
Applicant record in the Admin ATS.

An applicant reply can be correlated back to its source application via three
signals, evaluated in strict priority order:

  1. **Plus-addressed To**: the outbound confirmation email sets
     ``Reply-To: hiring+{application_id}@realaicoach.app``. Modern MTAs deliver
     mail sent to ``hiring+ANYTHING@...`` into the ``hiring@`` inbox. This is
     the strongest signal because it is injected by our own system and cannot
     be spoofed/forwarded away on reply.

  2. **Subject token**: the subject line contains ``[APP-XXXX]``; most mail
     clients preserve this on reply (``Re: ... [APP-XXXX]``). This is our
     fallback when a mail client strips the Reply-To plus-address.

  3. **In-Reply-To / References header lookup**: RFC 5322 mail clients cite
     the original ``Message-ID`` on reply. We store the outbound Message-ID
     alongside the application and look up the application that way.

All three extractors are pure functions — the thread webhook route composes
them. They are unit-tested independently to guarantee predictable priority.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# Supported application-id formats in production:
# - legacy: APP-XXXX style
# - current: app_xxxxxxxx style (emitted by /api/careers/apply)
_APP_ID_RE = re.compile(
    r"(?:APP-[A-Z0-9][A-Z0-9\-]{3,}|app_[a-z0-9][a-z0-9_\-]{5,})",
    re.IGNORECASE,
)
_PLUS_ADDR_RE = re.compile(
    r"(?:^|<|\s)([A-Za-z0-9._%+\-]+)\+([A-Za-z0-9._\-]+)@([A-Za-z0-9.\-]+)(?:\s|>|$|,)"
)


def extract_app_id_from_plus_addr(to_list: Iterable[str]) -> Optional[str]:
    """Return the application_id encoded in a ``hiring+APP-XXX@...`` address.

    Only accepts the canonical ``hiring`` local-part so that arbitrary inbox
    aliases (eg. ``admin+foo@``) do not become correlation vectors.
    """
    for entry in to_list or []:
        if not entry:
            continue
        m = _PLUS_ADDR_RE.search(str(entry))
        if not m:
            continue
        local, plus_tag, _domain = m.group(1), m.group(2), m.group(3)
        if local.lower() != "hiring":
            continue
        candidate_raw = str(plus_tag or "").strip()
        if not candidate_raw:
            continue

        candidate_upper = candidate_raw.upper()
        if candidate_upper.startswith("APP-") and len(candidate_upper) >= 7:
            return candidate_upper

        candidate_lower = candidate_raw.lower()
        if candidate_lower.startswith("app_") and len(candidate_lower) >= 9:
            return candidate_lower
    return None


def extract_app_id_from_subject(subject: str) -> Optional[str]:
    """Return the first ``APP-...`` token found in the subject line."""
    if not subject:
        return None
    m = _APP_ID_RE.search(subject)
    if not m:
        return None
    token = m.group(0)
    return token.lower() if token.lower().startswith("app_") else token.upper()


def parse_message_id_refs(header_value: str) -> list[str]:
    """Parse ``In-Reply-To`` / ``References`` header values into Message-IDs.

    Header values are space-separated ``<id>`` tokens. We return the raw
    bracketed form since that's what the outbound provider stores.
    """
    if not header_value:
        return []
    refs = re.findall(r"<[^<>\s]+>", header_value)
    # Some providers store without angle brackets — accept those too.
    if not refs:
        refs = [tok for tok in header_value.split() if tok.strip()]
    return [r.strip() for r in refs if r.strip()]


def correlate_inbound(
    to_list: Iterable[str],
    subject: str,
    in_reply_to: str = "",
    references: str = "",
) -> tuple[Optional[str], str]:
    """Run the full correlation pipeline. Returns ``(app_id, signal)``.

    ``signal`` is one of ``"plus_addr"``, ``"subject_token"``,
    ``"message_id_refs"``, or ``""`` when no correlation is possible.

    ``message_id_refs`` signal requires a database lookup the caller performs
    using the Message-IDs returned in the second element of the tuple.
    """
    plus = extract_app_id_from_plus_addr(to_list)
    if plus:
        return plus, "plus_addr"

    subj = extract_app_id_from_subject(subject)
    if subj:
        return subj, "subject_token"

    refs = parse_message_id_refs(in_reply_to) + parse_message_id_refs(references)
    if refs:
        # Caller must look up these refs against the outbound message log.
        # Encode them into the signal for the caller's convenience.
        return None, "message_id_refs:" + ",".join(refs)

    return None, ""


__all__ = [
    "extract_app_id_from_plus_addr",
    "extract_app_id_from_subject",
    "parse_message_id_refs",
    "correlate_inbound",
]
