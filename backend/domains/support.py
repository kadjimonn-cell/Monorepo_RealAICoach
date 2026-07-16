"""Support Domain — Tickets, SLA, escalation, FAQ, help, direct messages."""
from fastapi import APIRouter


def register(api_router: APIRouter, app=None):
    from routes import tickets
    from routes import sla_engine
    from routes import direct_messages
    from routes import support
    from routes import ticket_email_mgmt
    from routes.escalation_engine import router as escalation_router

    api_router.include_router(tickets.router, tags=["Support Tickets"])
    api_router.include_router(sla_engine.router, tags=["SLA Engine"])
    api_router.include_router(direct_messages.router, tags=["Direct Messages"])
    api_router.include_router(escalation_router, prefix="/admin/manage", tags=["Escalation Engine"])

    if app:
        app.include_router(support.router, prefix="/api", tags=["Support"])
        app.include_router(ticket_email_mgmt.router, prefix="/api", tags=["Ticket Email Management"])
