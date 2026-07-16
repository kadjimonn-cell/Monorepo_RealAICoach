# 🛑 ZERO ASSUMPTIONS POLICY — ENFORCED · GLOBAL · NON-BYPASSABLE

> **This is a binding, globally-enforced rule for every agent, every iteration.**
> Violating it is a **blocking regression**. Do not proceed past any violation.

---

## 1. The Rule (verbatim, non-negotiable)

> **Never fabricate, guess, infer, placeholder, or "seed for testing" any data that
> represents a real business identity.**
>
> All Legal Business Name, Registered HQ Address, CEO / Executive Name, CEO Title,
> CEO Signature, Official Logo, Company Contact email/phone/website, and any other
> platform identity fields **MUST** be loaded from verified platform source-of-truth
> locations. If the data is missing, **STOP and ask the user. Do not invent.**

This rule applies universally — PDF generators, email templates, receipts, contracts,
certificates, invoices, legal notices, dashboards, AI responses, documentation, tests,
seed scripts, and any code path that emits platform identity to a user or file.

---

## 2. Violation history (do not repeat)

| Date | Violation | Consequence |
|---|---|---|
| Apr 21, 2026 | Seeded `settings.offer_branding` with fabricated CEO `"Samir Patel"` and address `"2261 Market Street, Suite 5000, San Francisco, CA 94114, USA"` and legal name `"RealAICoach, Inc."` instead of searching the codebase for the already-existing platform constants. | Full rebuild of branding layer. Apology issued. Guardrails added (this document + 3 enforcement layers). |

### 🚫 Forbidden fabricated tokens (CI-enforced — will fail the build)
- `Samir Patel`
- `2261 Market Street`
- `2261 Market St,`
- `San Francisco, CA 94114`
- `RealAICoach, Inc.`  *(note the comma — the real entity is `RealAICoach LLC`)*
- `Morgan Chen, CTO` *(only forbidden in DB/default settings — OK as a sample in per-offer fields)*

Any code-path or DB document containing these strings will fail
`tests/test_zero_assumptions_guard.py` and block deployment.

---

## 3. Canonical Source-of-Truth Table (platform identity)

| Field | Authoritative Value | Source file (single source of truth) |
|---|---|---|
| Legal Business Name | `RealAICoach LLC` | `routes/careers_offers.py::_PLATFORM_LEGAL_NAME` (mirrored in `utils/email_templates.py`, `brand_protection.py`, `utils/global_email_footer.html`, `payments.py`, etc.) |
| Registered HQ Address | `11501 Domain Dr, Suite 200, Austin, TX 78758, USA` | `routes/careers_offers.py::_PLATFORM_HQ_ADDRESS` |
| CEO Full Name | `Adjimon Kouatonou` | `routes/ai_learning_hub.py::CERTIFICATE_SIGNER_NAME` |
| CEO Title | `Chief Executive Officer (CEO)` | `routes/ai_learning_hub.py::CERTIFICATE_SIGNER_ROLE` |
| CEO Handwritten Signature | `/app/backend/static/branding/adjimon-signature-handwritten.png` | `routes/ai_learning_hub.py::CERTIFICATE_HANDWRITTEN_SIGNATURE_PATH` |
| Official Logo (branded) | `/app/backend/static/branding/realaicoach-logo.png` | `routes/ai_learning_hub.py::CERTIFICATE_BRAND_LOGO_PATH` |
| Support / Contact Email | `support@realaicoach.app` | `settings.receipt_branding.company_info` |
| Hiring Email | `hiring@realaicoach.app` | PDF header (careers_offers.py header helper) |
| Careers Email | `careers@realaicoach.app` | PDF header (careers_offers.py header helper) |
| Brand Name (display) | `RealAICoach` | `settings.receipt_branding.brand_name` |

**If the field you need is not in this table, search the codebase before asking.**

---

## 4. Required workflow (every agent, every time)

```
Need a business-identity value?
    ↓
1. Search the codebase FIRST:
     grep -rnE "(CERTIFICATE_SIGNER|LEGAL_NAME|HQ_ADDRESS|_PLATFORM_|brand_name)" /app/backend
     grep -rnE "(RealAICoach|realaicoach\.app)" /app/backend
    ↓
2. If found → use that constant / read from that source.  STOP.
    ↓
3. If NOT found → ASK THE USER for the value via ask_human.  STOP.
    ↓
4. NEVER: invent placeholder, use "Lorem Ipsum", copy a sample from training data,
   or "seed for testing purposes". If you catch yourself about to type a name
   or address you didn't read from a file — STOP.
```

---

## 5. Enforcement — 3 automated layers

1. **Static guard (CI blocker)**: `/app/backend/tests/test_zero_assumptions_guard.py`
   greps the entire backend for forbidden fabricated tokens. Fails build on match.

2. **Runtime guard (request-time)**: `routes/careers_offers.py::_assert_no_fabrication`
   validates every loaded branding doc before it renders a PDF. Raises
   `FabricatedDataViolation` (HTTP 500 with clear log) if forbidden tokens sneak in.

3. **DB scrubber (startup)**: `routes/careers_offers.py::_scrub_fabricated_branding`
   on app boot, scans `settings.offer_branding` and `settings.receipt_branding` for
   forbidden tokens; logs and auto-removes the offending doc so the layered default
   kicks in.

4. **Regression guard (identity)**: existing
   `tests/test_offer_pdf_regression_guard.py` asserts real values ARE present in
   every generated PDF — the positive counterpart to the negative guard.

---

## 6. Handoff instruction for future agents

> **READ `/app/memory/ZERO_ASSUMPTIONS_POLICY.md` BEFORE WRITING ANY CODE THAT
> EMITS BUSINESS-IDENTITY DATA.** If in doubt, run
> `pytest tests/test_zero_assumptions_guard.py` before finishing any task.
