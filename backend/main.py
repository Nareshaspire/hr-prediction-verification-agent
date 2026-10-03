import asyncio
import csv
import io
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Response, status
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI
from prisma import Json, Prisma
from pydantic import BaseModel, Field, field_validator

MAX_RESUME_CHARS = 3_500
MAX_COMPLETION_TOKENS = 180
LLM_TIMEOUT_SECONDS = 150.0
PROMPT_VERSION = "recruiter-workflow-v2"
PIPELINE_STAGES = {"New", "Reviewed", "Interview", "Decision", "Archived"}

NANU_MODE_PROMPTS = {
    "Ask": (
        "You are Nanu, a knowledgeable technical assistant focused on answering questions and "
        "providing information about software development, technology, and related topics. "
        "Produce a concise interview-preparation brief. Analyze the candidate's technical skills, "
        "explain requirement alignments, and provide exactly three targeted interview questions. "
        "Do not make automated hiring or rejection recommendations."
    ),
    "Plan": (
        "You are Nanu, an experienced technical leader who is inquisitive and an excellent planner. "
        "Produce a structured interview-preparation brief and assessment plan. Analyze requirement "
        "coverage, identify ambiguities to validate during screening, and outline exactly three "
        "probing technical evaluation questions. Do not make automated hiring or rejection recommendations."
    ),
    "Agent": (
        "You are Nanu, a highly skilled software engineer with extensive knowledge in many "
        "programming languages, frameworks, design patterns, and best practices. "
        "Produce a technical interview-preparation brief focused on practical execution depth, "
        "architectural patterns, and hands-on competencies. Provide exactly three technical validation "
        "questions. Do not make automated hiring or rejection recommendations."
    ),
}

db = Prisma()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "granite3.3:2b")
http_client = httpx.AsyncClient(timeout=httpx.Timeout(LLM_TIMEOUT_SECONDS, connect=5.0))
client = AsyncOpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="ollama",
    http_client=http_client,
    max_retries=0,
)
inference_lock = asyncio.Lock()

app = FastAPI(title="Recruiter Workflow Copilot", version="2.1.0")


class JobRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=120)
    department: str | None = Field(None, max_length=120)
    location: str | None = Field(None, max_length=120)
    description: str = Field(..., min_length=20, max_length=6_000)
    must_have_skills: list[str] = Field(default_factory=list, max_length=20)
    preferred_skills: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("must_have_skills", "preferred_skills")
    @classmethod
    def clean_skills(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class CandidateRequest(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=120)
    resume_text: str = Field(..., min_length=20, max_length=MAX_RESUME_CHARS)
    consent_acknowledged: bool
    nanu_role: str | None = Field(default="Ask", max_length=50)

    @field_validator("resume_text")
    @classmethod
    def clean_resume(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Resume text cannot be empty.")
        return value


class StageRequest(BaseModel):
    stage: str
    actor: str = Field(default="Recruiter", max_length=120)

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, value: str) -> str:
        if value not in PIPELINE_STAGES:
            raise ValueError(f"Stage must be one of: {', '.join(sorted(PIPELINE_STAGES))}")
        return value


class ReviewRequest(BaseModel):
    action: str = Field(..., min_length=2, max_length=120)
    recruiter: str = Field(default="Recruiter", max_length=120)
    recruiter_notes: str | None = Field(None, max_length=4_000)
    scorecard: dict[str, int] = Field(default_factory=dict)


@app.on_event("startup")
async def startup() -> None:
    await db.connect()


@app.on_event("shutdown")
async def shutdown() -> None:
    if db.is_connected():
        await db.disconnect()
    await http_client.aclose()


def sanitize_pii(text: str) -> str:
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", text)
    return re.sub(r"\b(?:\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b", "[REDACTED_PHONE]", text)


def find_evidence(text: str, skill: str) -> str | None:
    for sentence in re.split(r"(?<=[.!?\n])\s+", text):
        if skill.lower() in sentence.lower():
            return sentence.strip()[:280]
    return None


def requirement_coverage(text: str, job: Any) -> list[dict[str, str]]:
    coverage: list[dict[str, str]] = []
    for skill in job.must_have_skills:
        evidence = find_evidence(text, skill)
        coverage.append({
            "requirement": skill,
            "priority": "Must have",
            "status": "Evidenced" if evidence else "Unclear",
            "evidence": evidence or "No direct evidence found in supplied resume.",
        })
    for skill in job.preferred_skills:
        evidence = find_evidence(text, skill)
        coverage.append({
            "requirement": skill,
            "priority": "Preferred",
            "status": "Evidenced" if evidence else "Unclear",
            "evidence": evidence or "No direct evidence found in supplied resume.",
        })
    return coverage


def preparation_confidence(coverage: list[dict[str, str]], resume: str) -> float:
    if not coverage:
        return round(min(55 + len(resume.split()) / 20, 75), 1)
    must = [item for item in coverage if item["priority"] == "Must have"]
    preferred = [item for item in coverage if item["priority"] == "Preferred"]
    must_score = sum(item["status"] == "Evidenced" for item in must) / max(len(must), 1)
    preferred_score = sum(item["status"] == "Evidenced" for item in preferred) / max(len(preferred), 1)
    return round(min(50 + must_score * 35 + preferred_score * 10 + min(len(resume.split()), 150) / 30, 95), 1)


async def audit(applicant_id: str, action: str, actor: str = "System", metadata: dict | None = None) -> None:
    meta_json = Json(metadata) if metadata else None
    await db.auditevent.create(data={
        "applicant": {"connect": {"id": applicant_id}},
        "action": action,
        "actor": actor,
        "metadata": meta_json,
    })


async def get_job_or_404(job_id: str) -> Any:
    job = await db.job.find_unique(where={"id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job requisition not found.")
    return job


async def get_applicant_or_404(applicant_id: str) -> Any:
    applicant = await db.applicant.find_unique(
        where={"id": applicant_id},
        include={"job": True, "credentials": True, "feedback_logs": True, "audit_events": True},
    )
    if not applicant:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return applicant


@app.get("/health")
async def health_check() -> dict:
    return {"status": "healthy", "service": "recruiter-workflow-backend", "model": OLLAMA_MODEL}


@app.get("/ready")
async def readiness_check() -> dict:
    if not db.is_connected():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is not connected.")
    return {"status": "ready", "database": "connected", "model": OLLAMA_MODEL}


@app.get("/api/v1/jobs")
async def list_jobs() -> list[dict]:
    jobs = await db.job.find_many(order={"created_at": "desc"}, include={"applicants": True})
    return [
        {
            "id": job.id,
            "title": job.title,
            "department": job.department,
            "location": job.location,
            "status": job.status,
            "applicant_count": len(job.applicants),
            "created_at": job.created_at.isoformat(),
        }
        for job in jobs
    ]


@app.post("/api/v1/jobs", status_code=status.HTTP_201_CREATED)
async def create_job(payload: JobRequest) -> dict:
    job = await db.job.create(data=payload.model_dump())
    return {"id": job.id, "title": job.title, "status": job.status}


@app.get("/api/v1/jobs/{job_id}")
async def job_detail(job_id: str) -> dict:
    job = await get_job_or_404(job_id)
    return {
        "id": job.id,
        "title": job.title,
        "department": job.department,
        "location": job.location,
        "description": job.description,
        "must_have_skills": job.must_have_skills,
        "preferred_skills": job.preferred_skills,
        "status": job.status,
    }


@app.post("/api/v1/jobs/{job_id}/candidates", status_code=status.HTTP_201_CREATED)
async def analyze_candidate(job_id: str, payload: CandidateRequest) -> dict:
    if not payload.consent_acknowledged:
        raise HTTPException(status_code=422, detail="Candidate notice/consent acknowledgement is required before analysis.")
    job = await get_job_or_404(job_id)
    sanitized_resume = sanitize_pii(payload.resume_text)
    coverage = requirement_coverage(sanitized_resume, job)
    confidence = preparation_confidence(coverage, sanitized_resume)

    active_mode = payload.nanu_role or "Ask"
    if active_mode not in NANU_MODE_PROMPTS:
        raise HTTPException(status_code=422, detail=f"Nanu role must be one of: {', '.join(NANU_MODE_PROMPTS.keys())}")
    system_instruction = NANU_MODE_PROMPTS[active_mode]

    try:
        async with inference_lock:
            response = await client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {
                        "role": "user",
                        "content": (
                            f"Role: {job.title}\n"
                            f"Must-have skills: {', '.join(job.must_have_skills) or 'None specified'}\n"
                            f"Preferred skills: {', '.join(job.preferred_skills) or 'None specified'}\n\n"
                            f"Candidate Resume:\n{sanitized_resume}"
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=MAX_COMPLETION_TOKENS,
            )
        brief = response.choices[0].message.content
        if not brief:
            raise HTTPException(status_code=502, detail="The model returned an empty response.")
        
        # Connect job relation and wrap JSON dictionary
        applicant = await db.applicant.create(data={
            "job": {"connect": {"id": job.id}},
            "display_name": payload.display_name,
            "original_text": sanitized_resume,
            "consent_acknowledged": True,
            "retention_until": datetime.now(timezone.utc) + timedelta(days=90),
            "analysis_json": Json({"coverage": coverage, "nanu_mode": active_mode}),
            "model_name": OLLAMA_MODEL,
            "prompt_version": PROMPT_VERSION,
        })
        credential = await db.parsedcredential.create(data={
            "applicant": {"connect": {"id": applicant.id}},
            "credential_type": f"{active_mode} Mode interview brief",
            "extracted_text": brief,
            "confidence_score": confidence,
            "authenticity_tier": "Recruiter review required",
        })
        await audit(
            applicant.id,
            f"Candidate analyzed ({active_mode} mode)",
            metadata={"job_id": job.id, "model": OLLAMA_MODEL, "prompt_version": PROMPT_VERSION, "mode": active_mode},
        )
        return {
            "id": applicant.id,
            "stage": applicant.stage,
            "preparation_confidence": credential.confidence_score,
            "coverage": coverage,
            "interview_brief": brief,
            "retention_until": applicant.retention_until.isoformat(),
        }
    except APITimeoutError:
        raise HTTPException(status_code=504, detail="The local model took too long. Use a shorter resume and retry.")
    except APIConnectionError:
        raise HTTPException(status_code=503, detail="Could not connect to the local Ollama service.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database or inference pipeline error: {str(exc)}")


@app.get("/api/v1/jobs/{job_id}/candidates")
async def list_candidates(job_id: str) -> list[dict]:
    await get_job_or_404(job_id)
    applicants = await db.applicant.find_many(where={"job_id": job_id}, order={"created_at": "desc"}, include={"credentials": True})
    return [
        {
            "id": item.id,
            "name": item.display_name,
            "stage": item.stage,
            "preparation_confidence": item.credentials[0].confidence_score if item.credentials else None,
            "created_at": item.created_at.isoformat(),
        }
        for item in applicants
    ]


@app.get("/api/v1/candidates/{applicant_id}")
async def candidate_detail(applicant_id: str) -> dict:
    candidate = await get_applicant_or_404(applicant_id)
    brief = candidate.credentials[0] if candidate.credentials else None
    return {
        "id": candidate.id,
        "name": candidate.display_name,
        "stage": candidate.stage,
        "job": {"id": candidate.job.id, "title": candidate.job.title} if candidate.job else None,
        "coverage": (candidate.analysis_json or {}).get("coverage", []),
        "interview_brief": brief.extracted_text if brief else None,
        "preparation_confidence": brief.confidence_score if brief else None,
        "retention_until": candidate.retention_until.isoformat() if candidate.retention_until else None,
        "reviews": [
            {
                "action": review.action,
                "recruiter": review.recruiter,
                "notes": review.recruiter_notes,
                "scorecard": review.scorecard,
                "timestamp": review.timestamp.isoformat(),
            }
            for review in candidate.feedback_logs
        ],
        "audit_events": [
            {
                "action": event.action,
                "actor": event.actor,
                "metadata": event.metadata,
                "timestamp": event.timestamp.isoformat(),
            }
            for event in candidate.audit_events
        ],
    }


@app.patch("/api/v1/candidates/{applicant_id}/stage")
async def change_stage(applicant_id: str, payload: StageRequest) -> dict:
    candidate = await get_applicant_or_404(applicant_id)
    updated = await db.applicant.update(where={"id": candidate.id}, data={"stage": payload.stage})
    await audit(candidate.id, f"Stage changed to {payload.stage}", payload.actor, {"previous_stage": candidate.stage})
    return {"id": updated.id, "stage": updated.stage}


@app.post("/api/v1/candidates/{applicant_id}/reviews", status_code=status.HTTP_201_CREATED)
async def add_review(applicant_id: str, payload: ReviewRequest) -> dict:
    candidate = await get_applicant_or_404(applicant_id)
    review = await db.hitlfeedback.create(data={
        "applicant": {"connect": {"id": candidate.id}},
        "action": payload.action,
        "recruiter": payload.recruiter,
        "recruiter_notes": payload.recruiter_notes,
        "scorecard": Json(payload.scorecard),
    })
    await audit(candidate.id, "Recruiter review recorded", payload.recruiter, {"action": payload.action})
    return {"id": review.id, "timestamp": review.timestamp.isoformat()}


@app.get("/api/v1/jobs/{job_id}/export.csv")
async def export_candidates(job_id: str) -> Response:
    job = await get_job_or_404(job_id)
    candidates = await db.applicant.find_many(where={"job_id": job.id}, include={"credentials": True})
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Candidate", "Stage", "Preparation confidence", "Created at"])
    for candidate in candidates:
        confidence = candidate.credentials[0].confidence_score if candidate.credentials else ""
        writer.writerow([candidate.display_name or "", candidate.stage, confidence, candidate.created_at.isoformat()])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{job.title.lower().replace(" ", "-")}-candidates.csv"'},
    )


@app.get("/api/v1/integrations")
async def integration_status() -> dict:
    return {
        "ats": "Not connected",
        "message": "ATS connections require customer-managed OAuth credentials and are intentionally not enabled in this local deployment.",
    }
