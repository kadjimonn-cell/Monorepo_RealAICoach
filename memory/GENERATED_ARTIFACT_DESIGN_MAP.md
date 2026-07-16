# Generated Artifact Design Map

## Purpose
Internal source of truth for all generated RealAICoach artifacts so future work keeps one enterprise-grade visual rhythm across:

- Billing PDFs
- Invoice / receipt pages
- CSV helper/export pages
- Report-style admin exports
- Email notification templates
- Standalone report/alert emails

## Brand Source of Truth

### Primary Full Logo
- Static path: `/api/static/images/brand-logo-full.png`
- Local assets:
  - `/app/backend/static/images/brand-logo-full.png`
  - `/app/frontend/assets/images/brand-logo-full.png`

### Billing Document Treatment
- Use **compact white-chip logo treatment**
- Do not paste the large website-style logo directly into document headers
- Prefer structured document header rhythm over hero-style branding

## Shared Helpers

### Email helpers
- `backend/utils/email_service.py`
  - `render_email_logo(variant=...)`
  - `render_email_header_panel(...)`

### Email logo variants
- `default`
- `support`
- `security`
- `calendar`
- `report`
- `admin`
- `compact`

### Billing document logic
- `backend/routes/payments.py`
  - payment history PDF header
  - invoice / receipt PDF header
  - CSV helper page header

## Visual Rhythm Rules

### 1. Header hierarchy
Every generated artifact should follow this order:
1. Brand/logo block
2. Artifact title
3. Subtitle / purpose line
4. Meta pill or meta row

### 2. Logo usage
- **Billing documents:** compact chip treatment
- **Reports/admin exports:** report variant header panel
- **Security alerts:** security variant with stronger urgency accent
- **Support/account messages:** support variant
- **Calendar messages:** calendar variant

### 3. Meta presentation
Prefer one of:
- top-right meta pill
- inline meta row below header

Meta content examples:
- Generated timestamp
- Billing record date
- Report period
- Alert scope
- Document ID

### 4. Section spacing
- Outer shell padding: `24px–32px`
- Header bottom spacing: `16px–20px`
- Section block spacing: `20px–28px`
- Internal card padding: `14px–18px`

### 5. Borders and surfaces
- Use subtle border separation instead of harsh dividers
- Prefer rounded surfaces (`14px–24px` radius)
- Use enterprise light surfaces for helper/export pages
- Avoid oversized decorative gradients in document/report contexts

## Artifact Families

### A. Billing artifacts
Includes:
- Payment history PDF
- Invoice PDF
- Receipt PDF
- Payment export page
- Payment document page
- CSV helper page

Rules:
- compact logo chip
- metadata visible early
- title must dominate, logo must support
- no duplicate brand wordmark beside full logo unless necessary

### B. Shared email templates
Includes:
- templates in `backend/utils/email_templates.py`

Rules:
- use `_wrap(...)`
- maintain consistent account-communication footer
- use semantic accent by message type

### C. Standalone notification emails
Includes:
- anomaly alerts
- quality alerts
- audit exports
- hiring reports
- calendar emails
- admin/support replies

Rules:
- prefer `render_email_header_panel(...)`
- choose semantic variant by context
- use subtitle to explain purpose quickly
- use meta pill when timestamp/scope matters

## Do / Don’t

### Do
- keep logos compact in documents
- keep metadata structured and scannable
- keep title prominence above branding weight
- use one helper path when available
- preserve premium spacing

### Don’t
- paste oversized website logos into documents
- duplicate wordmark next to a full logo without purpose
- mix random border radii and paddings
- use raw standalone HTML blocks when a shared helper already exists
- let alerts/reports drift into multiple visual systems

## QA Checklist

Before shipping any new generated artifact, verify:

- correct logo helper or asset path used
- title / subtitle / meta hierarchy present
- spacing looks balanced on desktop email/PDF/export views
- no duplicate awkward branding
- artifact family matches the correct variant
- contrast is readable
- footer tone matches artifact type

## Current File Anchors

- `backend/utils/email_service.py`
- `backend/utils/email_templates.py`
- `backend/routes/payments.py`
- `backend/routes/performance_reports.py`
- `backend/routes/weekly_hiring_report.py`
- `backend/routes/admin_data_management.py`
- `backend/routes/core_platform.py`
- `backend/server.py`
- `frontend/app/payment-history-export-v2.tsx`
- `frontend/app/payment-document-v2.tsx`

## Update Policy

When adding a new generated artifact:
1. classify it as billing / support / security / calendar / report / admin
2. reuse the correct shared helper if possible
3. add the file to this map if it introduces a new artifact family or special case