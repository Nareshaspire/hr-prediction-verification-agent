# HR Prediction & Verification Agent

An AI-assisted recruiter workflow tool that generates evidence-based interview preparation briefs, requirement coverage analysis, and maintains a human-reviewed audit trail for hiring decisions.

## Features

- Create and manage job requisitions
- Analyze candidate resumes against required skills
- Generate interview-preparation briefs using a local model
- Record recruiter decisions and scorecards
- Maintain audit history for candidate workflow
- Redact PII before model input

## Architecture

- Frontend: Streamlit
- Backend: FastAPI
- Database: PostgreSQL
- ORM: Prisma
- LLM: Ollama
- Container orchestration: Docker Compose

## Tech Stack

- Python
- FastAPI
- Streamlit
- PostgreSQL
- Prisma
- Ollama
- Docker

## Prerequisites

- Docker and Docker Compose
- Ollama installed locally
- Optional: model downloaded locally

Example:
```bash
ollama pull granite3.3:2b
```

## Quick Start

1. Clone the repo:
```bash
git clone https://github.com/Nareshaspire/hr-prediction-verification-agent.git
cd hr-prediction-verification-agent
```

2. Copy the environment file:
```bash
cp .env.example .env
```

3. Start the stack:
```bash
docker compose up --build
```

4. Open the app:
- Frontend: http://localhost:8501
- Backend health: http://localhost:8000/health
- Backend ready: http://localhost:8000/ready

## Environment Variables

Use `.env.example` as the template.

Required:
- DATABASE_URL
- OLLAMA_BASE_URL
- OLLAMA_MODEL
- BACKEND_URL
- PRISMA_CACHE_DIR

## Typical Workflow

1. Create a job requisition
2. Add must-have and preferred skills
3. Enter candidate resume
4. Review AI-generated coverages and interview questions
5. Save recruiter scorecard and notes
6. Review the audit timeline and export candidate CSV

## Development

Run backend tests:
```bash
cd backend
pip install -r requirements.txt
pytest
```

Run the app locally without Docker:
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

And in another terminal:
```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

## Notes

This MVP is intended for human-in-the-loop recruiting support. The AI-generated brief should help recruiters prepare, not replace final hiring judgment.

## Troubleshooting

If backend is unavailable:
- check whether the backend container is running
- check Docker logs
- verify the database is healthy

If Ollama fails:
- ensure Ollama is running locally
- verify the model is available
- confirm `OLLAMA_BASE_URL` and `OLLAMA_MODEL`

If Postgres is unhealthy:
- wait for the DB container to become ready
- check the healthcheck in `docker-compose.yml`
