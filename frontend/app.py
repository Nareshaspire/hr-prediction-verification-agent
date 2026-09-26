import streamlit as st
import requests
from pypdf import PdfReader
import io

# Set page configuration
st.set_page_config(
    page_title="HR Prediction & Verification Agent", 
    page_icon="🤖", 
    layout="wide"
)

st.title("🤖 Autonomous HR Prediction & Verification Agent")
st.subheader("Upload a candidate PDF resume to generate contextual interview questions via local Ollama.")

# Backend API Endpoint URL targeting the container mesh network name
BACKEND_URL = "http://backend:8000/api/v1/extract"

# File Uploader Widget configured specifically for PDFs
uploaded_file = st.file_uploader("Choose a resume file (PDF format)", type=["pdf"])

if uploaded_file is not None:
    try:
        # Read the file into a byte stream wrapper for pypdf
        pdf_stream = io.BytesIO(uploaded_file.read())
        reader = PdfReader(pdf_stream)
        
        # Loop through all pages and extract text content
        extracted_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
        
        # Verify text was successfully extracted from the PDF layers
        if not extracted_text.strip():
            st.error("❌ Could not extract readable text from this PDF. It might be a scanned image or restricted file.")
        else:
            st.info("📄 PDF Resume text extracted successfully!")
            with st.expander("Preview Extracted Text"):
                st.text(extracted_text[:1000] + ("..." if len(extracted_text) > 1000 else ""))
                
            # Action button to trigger the analysis
            if st.button("🚀 Analyze Resume & Generate Questions"):
                with st.spinner("Analyzing resume credentials with Ollama (Llama3)... Please wait."):
                    
                    # Pack the text payload into the expected structure
                    payload = {"resume_text": extracted_text}
                    
                    try:
                        response = requests.post(BACKEND_URL, json=payload, timeout=60)
                        
                        if response.status_code == 200:
                            response_data = response.json()
                            
                            st.success("✅ Analysis Complete!")
                            
                            # Layout columns for displaying metadata metrics
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Status", response_data.get("status").upper())
                            col2.metric("Confidence Score", f"{response_data.get('confidence_score')}%")
                            col3.metric("Verification Tier", response_data.get("authenticity_tier"))
                            
                            st.write("---")
                            st.subheader("📋 Generated Interview Script & Questions")
                            st.markdown(response_data.get("interview_script"))
                            
                        elif response.status_code == 422:
                            st.error(f"❌ Backend Validation Error (422): Sent payload structure was rejected.")
                            st.json(response.json())
                        else:
                            st.error(f"❌ Backend Error ({response.status_code}): {response.text}")
                            
                    except requests.exceptions.ConnectionError:
                        st.error("❌ Connection Failed: Could not reach the backend API container.")
                    except Exception as e:
                        st.error(f"❌ An unexpected runtime error occurred: {str(e)}")
                        
    except Exception as e:
        st.error(f"Failed to process PDF file: {str(e)}")
else:
    st.write("Please upload a `.pdf` file containing the candidate's resume details to begin.")
