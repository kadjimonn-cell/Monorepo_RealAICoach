# PDF v15 for Attachment — Invoice (Design Only)

Status: DESIGN ONLY (No implementation)

## Goal
Define the Invoice document under the new global standard: **PDF v15 for attachment**.

## Required Structure
1. Header band
   - RealAICoach logo (left)
   - Document title: INVOICE (right)
   - Issue timestamp
2. Status chip row
   - Pending / Paid / Failed badge
3. Identity section
   - Bill To block
   - Document info block (Invoice ID, Transaction ID, Method, Timestamp)
4. Billing ledger
   - Plan charge
   - Tax
   - Processing fee
5. Total block
   - High-contrast summary amount
6. Verification footer
   - VERIFIED COPY marker
   - QR + hash signature + support contact

## Branding Tokens
- Blue header with consistent typography hierarchy
- Orange accent divider
- Light neutral card blocks
- Dark total row for financial emphasis

## Compliance
- Binary output must remain `%PDF-1.4`
- Must follow PDF v15 visual structure and spacing rhythm

## Verification Request to Admin
Please approve/reject this Invoice design baseline for PDF v15 attachment compliance.
