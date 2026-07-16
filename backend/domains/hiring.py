"""Hiring Domain — Jobs, employers, interviews, resume, ATS, and hiring intelligence."""
from fastapi import APIRouter


def register(api_router: APIRouter, app=None):
    from routes import jobs
    from routes import jobs_employer_console_realtime
    from routes import employers
    from routes import job_platform
    from routes import job_ai_services
    from routes import job_search
    from routes import hiring_intelligence
    from routes import interview_management
    from routes import resume_builder
    from routes import smart_scheduler
    from routes import video_interview
    from routes import realtime_intelligence
    from routes import fairness_ai
    from routes import interview_experience
    from routes import hiring_analytics
    from routes import predictive_timeline
    from routes import weekly_hiring_report
    from routes import ats_integrations
    from routes import hiring_v2

    api_router.include_router(jobs.router, tags=["Jobs"])
    api_router.include_router(jobs.router, prefix="/jobs-portal", tags=["Jobs Portal Jobs"])
    api_router.include_router(jobs_employer_console_realtime.router, tags=["Employer Console Realtime"])
    api_router.include_router(employers.router, tags=["Employers"])
    api_router.include_router(employers.router, prefix="/jobs-portal", tags=["Jobs Portal Employer Console"])
    api_router.include_router(job_platform.router, tags=["Job Platform"])
    api_router.include_router(job_platform.router, prefix="/jobs-portal", tags=["Jobs Portal Workflow"])
    api_router.include_router(job_ai_services.router, prefix="/jobs/ai", tags=["Job AI Services"])
    # Job Search mount: /api/jobs POSTs are hard-retired (410), so the AI services
    # are also exposed under the live /job-search namespace.
    api_router.include_router(job_ai_services.router, prefix="/job-search/ai", tags=["Job Search AI Services"])
    api_router.include_router(job_search.router, tags=["Job Search"])
    api_router.include_router(hiring_intelligence.router, tags=["ARIS Hiring Intelligence"])
    api_router.include_router(interview_management.router, tags=["Interview Management"])
    api_router.include_router(resume_builder.router, tags=["Career Tools"])
    api_router.include_router(smart_scheduler.router, tags=["Smart Scheduler & Automation"])
    api_router.include_router(video_interview.router, tags=["Video Interview Room"])
    api_router.include_router(realtime_intelligence.router, tags=["Real-Time Intelligence"])
    api_router.include_router(fairness_ai.router, tags=["Trust & Fairness AI"])
    api_router.include_router(interview_experience.router, tags=["Interview Summary & Experience"])
    api_router.include_router(hiring_analytics.router, tags=["Hiring Analytics"])
    api_router.include_router(predictive_timeline.router, tags=["Predictive Timeline"])
    api_router.include_router(weekly_hiring_report.router, tags=["Weekly Hiring Report"])
    api_router.include_router(ats_integrations.router, tags=["ATS Integrations"])
    api_router.include_router(hiring_v2.router, tags=["Hiring v2"])
