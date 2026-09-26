import os

import pandas as pd
import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
REQUEST_TIMEOUT = 180
STAGES = ["New", "Reviewed", "Interview", "Decision", "Archived"]

st.set_page_config(page_title="Recruiter Workflow Copilot", page_icon="🧭", layout="wide")


def api(method: str, path: str, **kwargs):
    response = requests.request(method, f"{BACKEND_URL}{path}", timeout=REQUEST_TIMEOUT, **kwargs)
    if not response.ok:
        detail = response.json().get("detail", response.text) if response.content else "Unknown error"
        raise RuntimeError(f"{response.status_code}: {detail}")
    return response


def load_jobs():
    try:
        return api("GET", "/api/v1/jobs").json()
    except Exception as error:
        st.error(f"Backend unavailable: {error}")
        return []


st.title("🧭 Recruiter Workflow Copilot")
st.caption("AI prepares evidence and interview questions. Recruiters review, decide, and retain the audit trail.")

with st.sidebar:
    st.header("New requisition")
    with st.form("new-job", clear_on_submit=True):
        title = st.text_input("Role title")
        department = st.text_input("Department")
        location = st.text_input("Location")
        description = st.text_area("Job description", height=150)
        must_have = st.text_input("Must-have skills", help="Comma-separated")
        preferred = st.text_input("Preferred skills", help="Comma-separated")
        create_job = st.form_submit_button("Create requisition", type="primary")
    if create_job:
        try:
            created = api("POST", "/api/v1/jobs", json={
                "title": title,
                "department": department or None,
                "location": location or None,
                "description": description,
                "must_have_skills": must_have.split(","),
                "preferred_skills": preferred.split(","),
            }).json()
            st.success(f"Created {created['title']}")
            st.rerun()
        except Exception as error:
            st.error(f"Could not create requisition: {error}")

jobs = load_jobs()
if not jobs:
    st.info("Create a requisition to start building an evidence-based interview workflow.")
    st.stop()

job_labels = {f"{job['title']} · {job['applicant_count']} candidates": job["id"] for job in jobs}
selected_label = st.selectbox("Active requisition", list(job_labels))
job_id = job_labels[selected_label]
job = api("GET", f"/api/v1/jobs/{job_id}").json()

header_left, header_right = st.columns([3, 1])
with header_left:
    st.subheader(job["title"])
    st.caption(" · ".join(value for value in [job.get("department"), job.get("location"), job["status"]] if value))
with header_right:
    st.download_button(
        "Export candidate CSV",
        data=api("GET", f"/api/v1/jobs/{job_id}/export.csv").content,
        file_name=f"{job['title'].lower().replace(' ', '-')}-candidates.csv",
        mime="text/csv",
    )

tab_candidates, tab_analyze, tab_review, tab_governance = st.tabs(["Candidates", "Analyze candidate", "Review & scorecard", "Governance"])

with tab_candidates:
    candidates = api("GET", f"/api/v1/jobs/{job_id}/candidates").json()
    if candidates:
        st.dataframe(pd.DataFrame(candidates).rename(columns={"name": "Candidate", "stage": "Pipeline stage", "preparation_confidence": "Preparation confidence", "created_at": "Created"}), hide_index=True, use_container_width=True)
    else:
        st.info("No candidates have been analyzed for this requisition.")

with tab_analyze:
    st.markdown("#### Create an interview-preparation brief")
    st.warning("Use this as recruiter support only. Do not use the generated text or score as an automated hiring decision.")
    with st.form("analyze-candidate", clear_on_submit=True):
        candidate_name = st.text_input("Candidate name or internal reference")
        consent = st.checkbox("I confirm the candidate has received the required notice and this analysis is for recruiter review.")
        resume = st.text_area("Resume text", height=260, max_chars=3500, help="Maximum 3,500 characters for reliable local CPU inference.")
        analyze = st.form_submit_button("Generate preparation brief", type="primary")
    if analyze:
        try:
            with st.spinner("Preparing evidence and interview questions with the local model..."):
                result = api("POST", f"/api/v1/jobs/{job_id}/candidates", json={"display_name": candidate_name, "resume_text": resume, "consent_acknowledged": consent}).json()
            st.success("Candidate logged and preparation brief created.")
            st.metric("Preparation confidence", f"{result['preparation_confidence']}%")
            st.dataframe(pd.DataFrame(result["coverage"]), hide_index=True, use_container_width=True)
            st.markdown(result["interview_brief"])
            st.caption(f"Retention review date: {result['retention_until']}")
        except Exception as error:
            st.error(f"Analysis failed: {error}")

with tab_review:
    candidates = api("GET", f"/api/v1/jobs/{job_id}/candidates").json()
    if not candidates:
        st.info("Analyze a candidate before recording a review.")
    else:
        candidate_lookup = {f"{item['name']} · {item['stage']}": item["id"] for item in candidates}
        candidate_id = candidate_lookup[st.selectbox("Candidate", list(candidate_lookup))]
        candidate = api("GET", f"/api/v1/candidates/{candidate_id}").json()
        metric_one, metric_two = st.columns(2)
        metric_one.metric("Preparation confidence", f"{candidate['preparation_confidence']}%")
        metric_two.metric("Pipeline stage", candidate["stage"])
        st.markdown("#### Requirement evidence")
        st.dataframe(pd.DataFrame(candidate["coverage"]), hide_index=True, use_container_width=True)
        st.markdown("#### Interview-preparation brief")
        st.markdown(candidate["interview_brief"])
        with st.form("review-form"):
            new_stage = st.selectbox("Pipeline stage", STAGES, index=STAGES.index(candidate["stage"]))
            action = st.selectbox("Review action", ["Reviewed", "Advance to interview", "Request clarification", "Archive candidate"])
            recruiter = st.text_input("Reviewer", value="Recruiter")
            notes = st.text_area("Reviewer notes")
            score_one, score_two, score_three = st.columns(3)
            technical = score_one.slider("Technical evidence", 1, 5, 3)
            communication = score_two.slider("Communication", 1, 5, 3)
            role_fit = score_three.slider("Role fit", 1, 5, 3)
            save_review = st.form_submit_button("Save recruiter review", type="primary")
        if save_review:
            try:
                api("PATCH", f"/api/v1/candidates/{candidate_id}/stage", json={"stage": new_stage, "actor": recruiter})
                api("POST", f"/api/v1/candidates/{candidate_id}/reviews", json={"action": action, "recruiter": recruiter, "recruiter_notes": notes or None, "scorecard": {"technical_evidence": technical, "communication": communication, "role_fit": role_fit}})
                st.success("Recruiter decision and scorecard saved.")
                st.rerun()
            except Exception as error:
                st.error(f"Could not save review: {error}")
        if candidate["reviews"]:
            st.markdown("#### Previous reviews")
            st.dataframe(pd.DataFrame(candidate["reviews"]), hide_index=True, use_container_width=True)

with tab_governance:
    st.markdown("#### Human-review policy")
    st.write("This workspace creates interview-preparation drafts only. Recruiters must review evidence, questions, scorecards, and every pipeline decision.")
    st.markdown("#### Audit timeline")
    candidates = api("GET", f"/api/v1/jobs/{job_id}/candidates").json()
    if candidates:
        candidate_lookup = {item["name"]: item["id"] for item in candidates}
        audit_candidate = candidate_lookup[st.selectbox("Candidate audit record", list(candidate_lookup), key="audit-candidate")]
        audit_record = api("GET", f"/api/v1/candidates/{audit_candidate}").json()
        st.dataframe(pd.DataFrame(audit_record["audit_events"]), hide_index=True, use_container_width=True)
        st.caption(f"Retention review date: {audit_record['retention_until']}")
    integration = api("GET", "/api/v1/integrations").json()
    st.markdown("#### ATS integration")
    st.info(f"{integration['ats']}: {integration['message']}")
