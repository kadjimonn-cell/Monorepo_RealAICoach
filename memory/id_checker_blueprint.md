# ID Checker — Enterprise Blueprint (v1)

## 1) Full System Architecture

### Runtime
- **Frontend**: Expo React Web (`/app/frontend`) 
- **Backend**: FastAPI (`/app/backend`) 
- **Database**: MongoDB
- **Storage**: Emergent Object Storage (secure document blobs)
- **Email/Notifications**: existing notification + email template services

### Core Domains
- **User Submission Domain**: profile + document intake + status tracking
- **AI Assist Domain**: OCR-like extraction, authenticity checks, risk scoring, recommendation
- **Admin Review Domain**: queue, case detail, decisions, suspend/override controls
- **Audit Domain**: state transitions, admin actions, messaging traceability

---

## 2) UI/UX Design (User + Admin)

### User UX (ID Checker page)
- Route: `/id-checker` (legacy `/id-verification` remains compatible)
- Mobile-first upload and document capture flow
- Inputs: Full Name, DOB, Country, ID Type, ID Number, Phone
- Status + progress chips:
  - `NOT_SUBMITTED`, `PENDING`, `AI_REVIEW`, `ADMIN_REVIEW`, `APPROVED`, `REJECTED`, `MORE_INFO_REQUIRED`
- Real-time status card states for approvals/rejections/more-info
- Re-submit support when rejected or more-info-required

### Admin UX
- Executive dashboard section renamed to **ID Checker**
- Queue endpoint supports filters (status/risk/country/date)
- Case detail endpoint includes:
  - front/back/selfie assets
  - extracted/vision findings
  - AI confidence/risk/suggested action
- Action panel via APIs:
  - approve / reject / more-info
  - suspend/ban via override action

---

## 3) Backend Structure (APIs + Schema)

### Route Namespace
- Primary namespace: `/api/id-checker/*`
- Legacy compatibility namespace: `/api/id-verification/*`

### Key APIs
- User:
  - `GET /api/id-checker/kyc/status`
  - `POST /api/id-checker/kyc/submit`
  - `POST /api/id-checker/kyc/upload-file`
  - `POST /api/id-checker/kyc/ai-verify`
- Admin:
  - `GET /api/id-checker/admin/queue`
  - `GET /api/id-checker/admin/case/{user_id}`
  - `POST /api/id-checker/admin/review/{user_id}`
  - `POST /api/id-checker/admin/override`
- Communication:
  - `POST /api/id-checker/messages`
  - `GET /api/id-checker/messages/{target_user_id}`

### Core Collections
- `afrikpay_kyc` (existing, extended for ID Checker)
  - `workflow_state` (strict state machine)
  - `status` (legacy compatibility)
  - `documents[]` (now includes `storage_path`, `storage_backend`)
  - `ai_verification`, `vision_analysis`, `combined_score`
- `id_checker_state_transitions`
  - transition log per state change (from/to, actor, reason, metadata)
- `id_checker_messages`
  - admin↔user in-app communication log

---

## 4) AI Integration Points

### AI Role (assist only)
- OCR-like data extraction from uploaded IDs
- Face/selfie vs ID checks
- Document authenticity/tamper signal collection
- Fraud risk and recommendation synthesis

### Decision Contract
- AI returns recommendations only
- **Final decision is always admin-controlled**

### Output Contract to Admin
- confidence score
- risk level (low/medium/high)
- suggested action (approve/review carefully/reject)

---

## 5) Verification Workflow Diagrams

### User Submission Workflow
`NOT_SUBMITTED -> PENDING -> AI_REVIEW -> ADMIN_REVIEW -> {APPROVED | REJECTED | MORE_INFO_REQUIRED}`

### Re-submit Workflow
`MORE_INFO_REQUIRED -> PENDING`

`REJECTED -> PENDING`

### Re-verification Workflow (risk/event triggered)
`APPROVED -> PENDING`

All transitions are logged and notification-triggered.

---

## 6) Admin Decision Flows

### Standard Decision Path
1. Open queue item
2. Review assets + extracted fields + AI scores
3. Choose decision:
   - Approve → `APPROVED`
   - Reject → `REJECTED`
   - Request More Info → `MORE_INFO_REQUIRED`
4. System logs transition + audit + sends notifications/email

### Override / Fraud Path
1. Admin override endpoint called
2. Action applied with transition logging
3. Optional suspension/ban metadata captured
4. User receives synchronized alerting

---

## Security + Compliance Notes
- Document uploads now use object storage paths (`storage_path`) 
- API access controlled via auth + admin checks
- State transitions are validated against strict allowed edges
- Action/decision trail is persisted for traceability
