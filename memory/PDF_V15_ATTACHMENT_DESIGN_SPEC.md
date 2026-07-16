# PDF v15 for Attachment — Global Design Specification (Step 1)

Date: 2026-04-27  
Status: DESIGN ONLY (No implementation yet)  
Workflow: Step 1 complete draft for admin verification

---

## 1) Objective

Define a single global attachment design standard named **PDF v15 for attachment** for:
- Payment History Statement
- Receipt
- Invoice

This is a **visual/layout branding standard**.  
Technical PDF byte version remains **PDF 1.4** for compatibility/enforcement.

---

## 2) Current Baseline (Validated)

Existing current files were verified from live platform routes:
- Receipt (existing/current)
- Invoice (existing/current)
- Payment History (existing/current)

Observed from approved screenshots:
- All render as PDF 1.4
- Layouts are close but not globally normalized to one formal v7-branded attachment spec

---

## 3) Naming + Versioning Rules

- **Design standard name:** `PDF v15 for attachment`
- **Technical compatibility:** must still emit `%PDF-1.4`
- Enforcement model:
  - Design rule: PDF v15
  - Binary rule: PDF 1.4

---

## 4) Global Design System (PDF v15)

### 4.1 Brand Tokens
- Primary: Royal blue header panel
- Accent: Orange separator strip
- Surface: light neutral gray cards
- Text hierarchy:
  - H1: document title (RECEIPT / INVOICE / PAYMENT HISTORY STATEMENT)
  - H2: section labels
  - Body: transaction details
  - Caption: metadata/footer

### 4.2 Core Structure (shared all 3 document types)
1. **Header band**
   - Left: RealAICoach logo + product line
   - Right: document type + issue date/time
2. **Status chip row**
   - Pending / Paid / Failed normalized badge style
3. **Identity block**
   - Bill To
   - Document info (ID, method, timestamp)
4. **Ledger table**
   - Description | Status | Amount
   - Tax + fees rows standardized
5. **Total block**
   - Strong contrast row for final amount
6. **Verification footer**
   - “VERIFIED COPY” stamp
   - QR + support/contact + hash signature metadata

### 4.3 Spacing + Layout Rules
- A4 portrait layout
- Uniform page margins
- Fixed vertical rhythm between blocks
- No clipped content on page 1
- Multi-page safe overflow for long ledgers

---

## 5) Document-Specific Rules

### 5.1 Receipt PDF v15
- Title: RECEIPT
- Mandatory fields:
  - Receipt ID
  - Transaction ID
  - Payment method label
  - Itemized tax and processing fee

### 5.2 Invoice PDF v15
- Title: INVOICE
- Mandatory fields:
  - Invoice ID
  - Billing entity block
  - Terms note area (if configured)

### 5.3 Payment History Statement PDF v15
- Title: PAYMENT HISTORY STATEMENT
- Mandatory summary cards:
  - Total paid
  - Transaction count
  - Succeeded count
  - Pending/failed split
- Ledger includes paginated transaction rows

---

## 6) Global Compliance Guardrails (No Regression)

1. Every attachment PDF in these flows must satisfy both:
   - `%PDF-1.4` header
   - PDF v15 layout components present
2. No route-specific ad-hoc style bypass for these 3 document families.
3. Validation gates:
   - Binary version check
   - Structural marker check (header block, status chip, ledger table, total block, verification footer)

---

## 7) Verification Checklist (Admin Sign-off)

Admin should confirm:
- [ ] Receipt visual matches PDF v15 standard
- [ ] Invoice visual matches PDF v15 standard
- [ ] Payment History visual matches PDF v15 standard
- [ ] All three remain `%PDF-1.4`
- [ ] No branding drift between documents

---

## 8) Implementation Not Started

Per enforced workflow, this is design-only.

No production code migration is performed yet.

Next step only after admin verification + user explicit approval.
