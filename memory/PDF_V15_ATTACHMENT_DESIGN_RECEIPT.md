# PDF v15 for Attachment — Receipt (Design Only)

Status: DESIGN ONLY (No implementation)

## Goal
Define the Receipt document under the new global standard: **PDF v15 for attachment**.

## Required Structure
1. Header band
   - RealAICoach logo (left)
   - Document title: RECEIPT (right)
   - Issue timestamp
2. Status chip row
   - Pending / Paid / Failed badge
3. Identity section
   - Bill To block
   - Document info block (Receipt ID, Transaction ID, Method, Timestamp)
4. Itemized ledger
   - Base subscription amount
   - Tax line
   - Processing fee line
5. Total block
   - High-contrast "TOTAL YOU PAY"
6. Verification footer
   - VERIFIED COPY marker
   - QR + hash signature + support contact

## Branding Tokens
- Blue primary header
- Orange accent divider
- Neutral gray body cards
- Strong dark total strip

## Compliance
- Binary output must remain `%PDF-1.4`
- Must follow PDF v15 layout structure above

## Verification Request to Admin
Please approve/reject this Receipt design baseline for PDF v15 attachment compliance.
