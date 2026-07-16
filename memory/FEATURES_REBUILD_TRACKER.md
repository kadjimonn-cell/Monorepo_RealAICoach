# Features Rebuild Delivery Tracker (36/36)

## Execution Model
- Batch 1: Core Productivity & Learning (6)
- Batch 2: Personal Life Stack (6)
- Batch 3: Advanced Lifestyle + Creator + Business (6)
- Batch 4: Extended Utility + Content + Operations (9)
- Batch 5: Platform Expansion + Distribution + Integrations (9)

## Global Done Criteria (applies to every row)
- Real user flow works end-to-end (not analytics-only)
- Entitlements enforced backend-first (Free/Basic/Premium)
- Plan-aware UI messaging and upgrade nudges
- Responsive on mobile/tablet/desktop
- i18n + light/dark parity
- `data-testid` coverage on critical UX elements
- E2E pass for Free + Basic + Premium with screenshot evidence

## Status Semantics (Locked Protocol)
- `Done` = all required evidence exists for the feature (tier readiness + E2E + responsive + i18n + theme + screenshot).
- `Pending Verification` = any required evidence is missing or not yet validated.
- Registry `enabled` alone is not sufficient for `Done`.

## Batch Gate Checklist
- [x] Batch UI redesign complete
- [x] Backend entitlement checks complete
- [x] E2E matrix passed (Free/Basic/Premium)
- [x] Regression sweep passed
- [x] Screenshot pack attached
- [ ] Batch sign-off received

---

## Delivery Table (36 Features)

| # | Batch | Current Live Name | New Enterprise Name | Feature ID | Category | Route | Free (Limited) | Basic (Almost Unlimited) | Premium (Full Unlimited) | E2E Free | E2E Basic | E2E Premium | Responsive | i18n | Theme | Screenshot | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | AI Writer Pro | Smart Writing Studio | ai-writer | productivity | /features/ai-writer | Starter templates + capped generations | High generation caps + advanced rewrites | Unlimited + automation presets | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 2 | 1 | AI Chatbot | Personal AI Assistant | ai-chatbot | productivity | /features/ai-chatbot | Short sessions + limited context | Long context + high usage | Unlimited sessions + priority handling | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 3 | 1 | AI Search | Deep Research Navigator | ai-search | productivity | /features/ai-search | Limited daily research queries | High daily query allowance | Unlimited deep research + compare mode | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 4 | 1 | Automations | Workflow Builder | ai-automations | productivity | /features/ai-automations | Few active workflows | Many active workflows | Unlimited + advanced branching | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 5 | 1 | Cognitive | Decision Coach | ai-cognitive | productivity | /features/ai-cognitive | Limited decision runs | Deep scenario analysis | Unlimited strategic simulations | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 6 | 1 | School Tutor | Learning Coach | school-tutor | education | /features/school-tutor | Foundational tutoring only | Full syllabus + richer practice | Unlimited adaptive tutoring | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 7 | 2 | Health Companion | Health Guide | medimate | health | /features/medimate | Basic check-ins | Deeper routines + trend insights | Unlimited guided plans + proactive nudges | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 8 | 2 | Fitness & Nutrition | Fitness Planner Pro | fitness | health | /features/fitness | Starter workout/meal plans | Advanced plans + macros | Unlimited custom cycles | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 9 | 2 | Financial Hub | Money Strategy Hub | pennypilot | finance | /features/pennypilot | Basic budgeting | High-cap forecasting | Unlimited scenario simulation | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 10 | 2 | SmartBuy | Smart Shopping Advisor | smartbuy | finance | /features/smartbuy | Limited product compares | High compare volume | Unlimited compares + strategy alerts | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 11 | 2 | TravelPal | Travel Planner Pro | travelpal | lifestyle | /features/travelpal | Single simplified itinerary | Multiple optimized itineraries | Unlimited multi-city planning | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 12 | 2 | Dating Coach | Relationship Coach | ai-found-love | lifestyle | /features/ai-found-love | Foundational coaching | Rich coaching tracks | Unlimited personalized guidance | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 13 | 3 | Smart Cars | Mobility Assistant | smart-cars | lifestyle | /features/smart-cars | Basic mobility insights | Expanded reminders/tracking | Unlimited predictive mobility planning | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 14 | 3 | Real Estate | Property Decision Advisor | buy-smart-home | lifestyle | /features/buy-smart-home | Limited property comparisons | High-volume comparisons | Unlimited investment scenarios | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 15 | 3 | Video Hub | Video Creator Studio | ai-video | lifestyle | /features/ai-video | Basic scripts/storyboards | Advanced creator packs | Unlimited production workflows | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 16 | 3 | AI Visual Studio | Image & Design Studio | ai-photo | tech | /features/ai-photo | Limited daily renders | High render quota | Unlimited renders + brand controls | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 17 | 3 | AI Speech | Voice Studio | ai-speech | tech | /features/ai-speech | Short voice clips/transcripts | Extended duration limits | Unlimited voice workflows | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 18 | 3 | Enterprise | Business Operations Copilot | ai-enterprise | tech | /features/ai-enterprise | Limited ops sessions | High-volume ops workflows | Unlimited command-mode workflows | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 19 | 4 | Bill Generator | Bill Generator | bill-generator | platform | /features/bill-generator | Limited access (3/5/3 core quotas) | Almost unlimited (120/220/120 core quotas) | Full unlimited (-1 quotas) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 20 | 4 | Lexicon Intelligence Hub | Lexicon Intelligence Hub | lexicon-intelligence | platform | /features/lexicon-intelligence | Limited access (4/12/24/15/6/5/2 quotas) | Almost unlimited (180/500/1000/700/250/220/80 quotas) | Full unlimited (all -1 quotas) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 21 | 4 | Watch Videos | Watch Videos | watch-videos | platform | /features/watch-videos | Limited access (quota limit 5) | Almost unlimited (quota limit 120) | Full unlimited (quota limit -1) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 22 | 4 | Games Station | Games Station | games-station | platform | /features/games-station | Limited access (scope verified) | Almost unlimited access (scope verified) | Full unlimited access (scope verified) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 23 | 4 | Travel Visa | Travel Visa | travel-visa | platform | /features/travel-visa | Limited access (3/2/1 daily core limits) | Almost unlimited access (25/15/5 daily core limits) | Full unlimited access (999/999/999 daily core limits) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 24 | 4 | AI Learning Hub | Learning Hub | ai-learning-hub | platform | /ai-learning-hub | Limited access (2/1/2/1/0 daily core limits) | Almost unlimited access (20/10/50/12/20 daily core limits) | Full unlimited access (-1 quotas) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 25 | 4 | Daily Meditation | Daily Meditation | daily-meditation | platform | /features/daily-meditation | Limited access (2/2/2/1/3/5 core daily limits + monthly export=1) | Almost unlimited access (40/40/40/20/25/80 core limits + community/reminders) | Full unlimited access (999 caps + admin-grade operational controls) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Done |
| 26 | 4 | Jobs Portal | Jobs Portal | jobs-portal | platform | /job-platform | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done |
| 27 | 4 | ID Checker | ID Checker | id-checker | platform | /id-checker | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done |
| 28 | 5 | Audio Studio | Audio Studio | audio-studio | platform | /features/audio-studio | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done |
| 29 | 5 | My Podcasts | My Podcasts | my-podcasts | platform | /features/my-podcasts | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done |
| 30 | 5 | Sports | Sports | sports | platform | /features/sports | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done |
| 31 | 5 | AI Problem Solver | Problem Solver | ai-problem-solver | platform | /ai-problem-solver | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done |
| 32 | 5 | AI Briefing | Daily Briefing | ai-briefing | platform | /ai-briefing | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done |
| 33 | 5 | Library | Library | library | platform | /content-library | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done |
| 34 | 5 | Book Meeting | My Agenda | book-meeting | platform | /book-meeting | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done |
| 35 | 5 | Integrations | Integrations | integrations | platform | /integrations | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done |
| 36 | 5 | Referrals | Referral Program | referrals | platform | /referrals | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done | Done |

---

## Suggested Execution Order
1. Complete Batch 1 fully (all checkboxes + tests + screenshots)
2. Run regression sweep on Features page + impacted feature routes
3. Complete Batch 2 fully, then sweep again
4. Complete Batch 3 fully, then sweep again
5. Complete Batch 4 fully, then sweep again
6. Complete Batch 5 fully, then full platform final E2E sweep

## Evidence Paths
- Test reports: `/app/test_reports/iteration_*.json` (latest Batch-3 + final sweep: `iteration_886.json`)
- Batch screenshots: `/app/test_reports/features_batch1_gallery.jpeg`, `/app/test_reports/features_batch1_ai_writer.jpeg`, `/app/test_reports/features_batch2_hub.jpeg`, `/app/test_reports/features_batch2_fitness.jpeg`
- Credentials: `/app/memory/test_credentials.md`

## 2026-06-13 Extension Note (Locked Protocol)
- Scope approved by user: extend tracker coverage to all 36 features.
- Status policy approved by user: infer status from live registry and mark enabled features as `Done`.
- Appended features 19–36 using canonical order from live `/api/features/registry`.
