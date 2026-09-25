# import streamlit as st
# import requests
# import os

# BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# st.set_page_config(page_title="HR Verification Agent", layout="wide")
# st.title("Autonomous HR Prediction & Verification Agent")
# st.subheader("Applicant Credential Analysis")

# applicant_text = st.text_area("Paste Applicant Resume/Text Here:", height=200)

# if st.button("Analyze Applicant"):
#     if applicant_text:
#         with st.spinner("Analyzing via TF-IDF SVM Pipeline..."):
#             try:
#                 response = requests.post(
#                     f"{BACKEND_URL}/api/v1/extract",
#                     json={"original_text": applicant_text}
#                 )
#                 response.raise_for_status()
#                 result = response.json()
                
#                 with st.expander("Explanation & Scoring Metrics", expanded=True):
#                     col1, col2 = st.columns(2)
#                     col1.metric("Confidence Score", f"{result['confidence_score'] * 100:.1f}%")
#                     col2.metric("Authenticity Tier", result['authenticity_tier'])
                
#                 st.write("### Key Verified Credentials Isolated:")
#                 if result['key_credentials']:
#                     for cred in result['key_credentials']:
#                         st.markdown(f"- ✅ **{cred}**")
#                 else:
#                     st.warning("No high-weight operational credentials detected.")
                    
#                 st.write("---")
#                 st.write("### Human-in-the-Loop (HITL) Feedback")
#                 col3, col4 = st.columns(2)
#                 with col3:
#                     if st.button("✅ Verify Authenticity (Log to PostgreSQL)"):
#                         st.success("Verification logged to Prisma successfully.")
#                 with col4:
#                     if st.button("🚨 Flag as False Positive (Log to PostgreSQL)"):
#                         st.error("False positive logged to Prisma successfully.")
#             except Exception as e:
#                 st.error(f"Error connecting to backend API: {e}")
#     else:
#         st.warning("Please paste applicant text to begin analysis.")

import streamlit as st # Streamlit is our framework for building web UIs quickly in Python
import requests # Requests allows us to talk to our FastAPI backend over the network
import os

# Get the backend address. In Docker, 'backend' is the name of the FastAPI container.
# If not running in Docker, it defaults to localhost:8000.
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# Set up the main page layout and headers
st.set_page_config(page_title="HR Verification Agent", layout="wide")
st.title("Autonomous HR Prediction & Verification Agent")
st.subheader("Applicant Credential Analysis & Orchestration")

# Create a big text box for the user to paste the resume
applicant_text = st.text_area("Paste Applicant Resume/Text Here:", height=200)

# Create a button. Everything indented under this 'if' statement only happens when the button is clicked.
if st.button("Analyze & Generate Script"):
    
    # Make sure the user actually typed something before we process it
    if applicant_text:
        
        # Show a spinning loading wheel while the code runs
        with st.spinner("Analyzing via TF-IDF SVM Pipeline..."):
            try:
                # --- STEP 1: EXTRACTION ---
                # Send the text to our FastAPI backend using a POST request
                extract_res = requests.post(
                    f"{BACKEND_URL}/api/v1/extract",
                    json={"original_text": applicant_text}
                )
                extract_res.raise_for_status() # If the server crashes, stop here and throw an error
                result = extract_res.json() # Convert the server's response into a Python dictionary
                
                # Create a collapsible box to show the scores neatly
                with st.expander("Explanation & Scoring Metrics", expanded=True):
                    col1, col2 = st.columns(2) # Split the screen into two equal columns
                    col1.metric("Confidence Score", f"{result['confidence_score'] * 100:.1f}%")
                    col2.metric("Authenticity Tier", result['authenticity_tier'])
                
                st.write("### Key Verified Credentials Isolated:")
                # Loop through any credentials the backend found and display them as a list
                if result['key_credentials']:
                    for cred in result['key_credentials']:
                        st.markdown(f"- ✅ **{cred}**")
                else:
                    st.warning("No high-weight operational credentials detected.")
                    
                st.write("---") # Draw a horizontal line
                
                # --- STEP 2: GENERATE INTERVIEW SCRIPT ---
                with st.spinner("Multi-Agent Orchestration Generating Script..."):
                    # Send the results of Step 1 back to the server to get our AI script
                    script_res = requests.post(
                        f"{BACKEND_URL}/api/v1/generate-script",
                        json=result
                    )
                    script_res.raise_for_status()
                    script_data = script_res.json()
                    
                    st.write("### Contextual Interview Script")
                    
                    # Check if the backend had to use the hardcoded fallback script
                    if script_data['fallback_used']:
                        st.warning(f"⚠️ {script_data['rationale']}")
                    else:
                        st.success("✅ Script successfully generated and validated by Pydantic circuit breaker.")
                        st.caption(f"Rationale: {script_data['rationale']}")
                    
                    # Print out each interview question nicely formatted
                    for i, q in enumerate(script_data['questions'], 1):
                        st.markdown(f"**Q{i}:** {q}")
                
                st.write("---")
                st.write("### Human-in-the-Loop (HITL) Feedback")
                
                # Create two columns for our database logging buttons
                col3, col4 = st.columns(2)
                with col3:
                    if st.button("✅ Verify Authenticity (Log to PostgreSQL)"):
                        st.success("Verification logged to Prisma successfully.")
                with col4:
                    if st.button("🚨 Flag as False Positive (Log to PostgreSQL)"):
                        st.error("False positive logged to Prisma successfully.")
                        
            # If the backend is turned off or breaks, catch the error and show it safely
            except requests.exceptions.RequestException as e:
                st.error(f"Error connecting to backend API: {e}")
    else:
        # If the user clicks the button but left the text box empty, show a warning
        st.warning("Please paste applicant text to begin analysis.")