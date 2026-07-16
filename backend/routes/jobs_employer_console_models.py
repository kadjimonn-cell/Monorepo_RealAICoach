"""Shared Employer Console request models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class InterviewKitShareRequest(BaseModel):
    panel_emails: List[str]
    note: Optional[str] = None


class OfferDraftRequest(BaseModel):
    application_id: str
    base_salary_usd: int = 120000
    start_date: str
    expires_at: str
    personal_message: Optional[str] = None


class OfferApprovalRequest(BaseModel):
    approver_name: Optional[str] = None
    note: Optional[str] = None


class OfferSendRequest(BaseModel):
    confirmation_url: Optional[str] = None


class OfferESignRequest(BaseModel):
    offer_token: str
    decision: str
    signer_name: str


class CopilotExecuteRequest(BaseModel):
    action_key: str
    note: Optional[str] = None


class BulkPipelineActionRequest(BaseModel):
    application_ids: List[str]
    action: str
    target_status: Optional[str] = None
    note: Optional[str] = None


class InterviewScorecardSubmitRequest(BaseModel):
    interview_id: Optional[str] = None
    technical_score: int = 3
    communication_score: int = 3
    problem_solving_score: int = 3
    culture_fit_score: int = 3
    strengths: List[str] = []
    concerns: List[str] = []
    recommendation: str = "lean_hire"
    debrief_summary: Optional[str] = None


class CommunicationSequenceStartRequest(BaseModel):
    channel: str = "email_inapp"
    track: str = "stage_progression"
    custom_opening: Optional[str] = None


class CommunicationSequenceAdvanceRequest(BaseModel):
    note: Optional[str] = None


class RediscoveryReengageRequest(BaseModel):
    job_id: Optional[str] = None
    message: Optional[str] = None


class SlaAutoTriggerRunRequest(BaseModel):
    application_id: Optional[str] = None
    max_items: int = 12