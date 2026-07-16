# Subscription Enforcement Matrix (Platform-Wide)

Last updated: 2026-03-21

## Role & Plan Rules

| Role/Plan | Access Level | Billing Actions | Admin Analytics | Expected Enforcement |
|---|---|---|---|---|
| Free user | Base features only | Can start checkout | No | 403/upgrade gate on paid routes |
| Basic user | Basic paid features | Upgrade/downgrade/cancel/reactivate | No | Active status + end-date validation |
| Premium user | Full paid features | Downgrade/cancel/reactivate | No | Active status + end-date validation |
| Admin | Full platform + admin tools | N/A | Yes | Admin-only endpoint guard |

## Core Subscription Lifecycle APIs

| Endpoint | Method | Auth | Rule |
|---|---|---|---|
| `/api/subscriptions/plans` | GET | Optional | Returns plan catalog |
| `/api/subscriptions/status` | GET | Required | Returns current user subscription |
| `/api/subscriptions/my-subscription` | GET | Required | User-owned subscription details only |
| `/api/subscriptions/create-checkout` | POST | Required | Creates provider checkout; no entitlement granted yet |
| `/api/subscriptions/checkout-status/{session_id}` | GET | Required | Returns checkout status; invalid session => 404 |
| `/api/payments/confirm` | POST | Required | **Hardened**: requires matching transaction + completed status |
| `/api/subscriptions/confirm-payment` | POST | Required | Alias to hardened confirm flow |
| `/api/subscriptions/cancel` | POST | Required | Cancels active paid subscription |
| `/api/subscriptions/reactivate` | POST | Required | Reactivates cancellable subscription |

## Provider Flow Rules

| Provider | Initiation | Completion Rule |
|---|---|---|
| Stripe | Checkout session | Must map to user transaction and `paid/completed/succeeded` |
| PayPal | Order + capture flow | Capture/verified transaction required before entitlement |
| FedaPay (mobile money) | Provider payment URL/session | Successful transaction status required before entitlement |

## Integrity Controls

| Control | Endpoint | Behavior |
|---|---|---|
| Nightly integrity auto-check | Triggered via admin overview load (once/day UTC) | Detects entitlement drift, missing end-date, expired-active users |
| Manual integrity run | `POST /api/admin/payment-analytics/subscriptions/integrity-check?auto_fix=true` | Generates report and applies safe auto-fixes |
| Latest integrity report | `GET /api/admin/payment-analytics/subscriptions/integrity-report/latest` | Summary for admin dashboard |
| Integrity history | `GET /api/admin/payment-analytics/subscriptions/integrity-report/history` | Audit trail of checks |

## E2E Verification Status

- Final E2E verification report: `/app/test_reports/iteration_1008.json`
- Security checks:
  - Fake payment confirmations blocked ✅
  - Unpaid confirm flow blocked ✅
  - Fake checkout status returns 404 ✅
- Mixed-content issues in subscription flows resolved ✅
- Responsive checks (mobile/tablet/desktop) passed ✅
