# from fastapi import FastAPI
# from pydantic import BaseModel
# from typing import List
# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.svm import SVC
# from sklearn.pipeline import Pipeline

# app = FastAPI(title="HR Prediction & Verification Agent API")

# class ApplicantData(BaseModel):
#     original_text: str

# class VerificationResponse(BaseModel):
#     confidence_score: float
#     authenticity_tier: str
#     key_credentials: List[str]

# # Initializing the SVM Pipeline prioritizing operational data
# training_texts = [
#     "warehouse forklift operator experience through January 2025",
#     "contract camp support worker roles",
#     "certified in Oracle Primavera P6 and SAP health and safety",
#     "passionate team player with synergistic generative leadership skills",
#     "highly motivated self-starter leveraging AI for dynamic synergies"
# ]
# # 1 = Verifiable Operational Data, 0 = Synthetic Generative Filler
# training_labels = [1, 1, 1, 0, 0]

# pipeline = Pipeline([
#     ('tfidf', TfidfVectorizer()),
#     ('clf', SVC(probability=True, kernel='rbf'))
# ])
# pipeline.fit(training_texts, training_labels)

# @app.post("/api/v1/extract", response_model=VerificationResponse)
# async def extract_credentials(data: ApplicantData):
#     text = data.original_text.lower()
    
#     # Calculate probability of being verifiable operational data
#     prob = pipeline.predict_proba([text])[0][1]
    
#     # Extract the specifically weighted target credentials
#     extracted = []
#     if "forklift" in text:
#         extracted.append("Warehouse Forklift Operator (verified through Jan 2025)")
#     if "camp support" in text:
#         extracted.append("Contract Camp Support Worker")
#     if "primavera p6" in text or "sap" in text:
#         extracted.append("Oracle Primavera P6 / SAP Health & Safety Certification")
        
#     tier = "High Probability Verifiable" if prob > 0.6 else "Synthetic Filler"
    
#     return VerificationResponse(
#         confidence_score=round(prob, 2),
#         authenticity_tier=tier,
#         key_credentials=extracted
#     )

# @app.get("/health")
# async def health_check():
#     return {"status": "healthy"}

# Import necessary tools and libraries
from fastapi import FastAPI, HTTPException # FastAPI is our web framework for creating the API
from pydantic import BaseModel, Field # Pydantic helps us define and enforce exact data structures
from typing import List, Optional # Typing hints help Python understand what kind of data to expect
from sklearn.feature_extraction.text import TfidfVectorizer # Converts text into numbers for our AI model
from sklearn.svm import SVC # The Support Vector Machine (SVM) algorithm we use to classify text
from sklearn.pipeline import Pipeline # Chains our text-converter and SVM model together
from google import genai # The official Google Gemini AI SDK
from google.genai import types # Allows us to configure specific Gemini API settings
import json
import os

# Initialize our FastAPI application. This is the engine that listens for web requests.
app = FastAPI(title="HR Prediction & Verification Agent API")

# Attempt to connect to the Google Gemini API. 
# It automatically looks for the GEMINI_API_KEY environment variable.
try:
    ai_client = genai.Client()
except Exception as e:
    ai_client = None
    print(f"Warning: Gemini client failed to initialize. {e}")

# --- DATA MODELS ---
# These classes act as strict "blueprints" for the data coming in and going out.
# If data doesn't match the blueprint, the API automatically rejects it.

class ApplicantData(BaseModel):
    original_text: str # We expect the user to send us a string of text (the resume)

class VerificationResponse(BaseModel):
    confidence_score: float # e.g., 0.95
    authenticity_tier: str # e.g., "High Probability Verifiable"
    key_credentials: List[str] # A list of strings, e.g., ["Forklift Operator"]

class InterviewScriptSchema(BaseModel):
    # Field descriptions guide the Gemini AI on exactly what we want it to generate
    questions: List[str] = Field(description="List of 3 to 5 targeted interview questions.")
    rationale: str = Field(description="Brief explanation of why these questions verify the extracted credentials.")

class ScriptResponse(BaseModel):
    questions: List[str]
    rationale: str
    fallback_used: bool # Tells the frontend if we had to use the hardcoded backup script
    retries: int # Tracks how many times the AI failed before succeeding

# --- HARDCODED BACKUP SCRIPT ---
# If the Gemini AI fails or the API key is missing, we use this safe, generic backup.
FALLBACK_SCRIPT = [
    "Can you describe your day-to-day responsibilities in your previous operational roles?",
    "What specific safety protocols and compliance standards did you follow?",
    "How did you apply your certifications in a practical, hands-on environment?"
]

# --- SVM MACHINE LEARNING PIPELINE ---
# 1. We provide examples of text we want to find (Operational data) and text we want to ignore (AI filler)
training_texts = [
    "warehouse forklift operator experience through January 2025",
    "contract camp support worker roles",
    "certified in Oracle Primavera P6 and SAP health and safety",
    "passionate team player with synergistic generative leadership skills",
    "highly motivated self-starter leveraging AI for dynamic synergies"
]
# 2. We label the examples: 1 = Good (Operational), 0 = Bad (Synthetic Filler)
training_labels = [1, 1, 1, 0, 0]

# 3. We create a pipeline that first turns the text into numbers (TF-IDF), then learns the patterns (SVC)
pipeline = Pipeline([
    ('tfidf', TfidfVectorizer()),
    ('clf', SVC(probability=True, kernel='rbf'))
])
# 4. Train the model right when the server starts up
pipeline.fit(training_texts, training_labels)

# --- API ENDPOINTS ---

# Endpoint 1: Extract credentials using our trained SVM model
@app.post("/api/v1/extract", response_model=VerificationResponse)
async def extract_credentials(data: ApplicantData):
    text = data.original_text.lower() # Convert everything to lowercase to make searching easier
    
    # Ask the SVM model: "What is the probability this is real operational data?"
    prob = pipeline.predict_proba([text])[0][1] 
    
    # Hardcoded extraction: manually pull out specific keywords if they exist in the text
    extracted = []
    if "forklift" in text:
        extracted.append("Warehouse Forklift Operator (verified through Jan 2025)")
    if "camp support" in text:
        extracted.append("Contract Camp Support Worker")
    if "primavera p6" in text or "sap" in text:
        extracted.append("Oracle Primavera P6 / SAP Health & Safety Certification")
        
    # Decide the tier based on the SVM's confidence score
    tier = "High Probability Verifiable" if prob > 0.6 else "Synthetic Filler"
    
    return VerificationResponse(
        confidence_score=round(prob, 2),
        authenticity_tier=tier,
        key_credentials=extracted
    )

# Endpoint 2: Generate an interview script using Google Gemini
@app.post("/api/v1/generate-script", response_model=ScriptResponse)
async def generate_interview_script(data: VerificationResponse):
    # Safety Check: Do we have an API client?
    if not ai_client:
        return ScriptResponse(questions=FALLBACK_SCRIPT, rationale="API Key missing. Using fallback.", fallback_used=True, retries=0)
    
    # Safety Check: Did the SVM actually find any credentials?
    if not data.key_credentials:
        return ScriptResponse(questions=FALLBACK_SCRIPT, rationale="No high-weight credentials to verify.", fallback_used=True, retries=0)

    # Prepare the context for the AI Agent
    analysis_context = f"Analyze these verified operational credentials: {', '.join(data.key_credentials)}. Identify the core practical skills required for these roles."
    
    # We will give the AI 3 chances to give us a perfectly formatted JSON response
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Combine the context with the specific instruction for generation
            prompt = f"{analysis_context}\nGenerate an interview script to explicitly verify these credentials. Do not reference generic AI or software skills."
            
            # Call the Gemini API
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", # Tell Gemini we ONLY want JSON back
                    response_schema=InterviewScriptSchema, # Force Gemini to match our Pydantic blueprint
                    temperature=0.2 # Lower temperature means more predictable, less "creative" answers
                ),
            )
            
            # The "Circuit Breaker": We run the AI's answer through our strict Pydantic blueprint.
            # If it fails, Python throws an Exception, and we jump down to the 'except' block to try again.
            validated_output = InterviewScriptSchema.model_validate_json(response.text)
            
            # If we get here, the AI succeeded! Return the data.
            return ScriptResponse(
                questions=validated_output.questions,
                rationale=validated_output.rationale,
                fallback_used=False,
                retries=attempt
            )
        except Exception as e:
            # The AI failed to format properly. Print the error and loop back to try again.
            print(f"Circuit breaker triggered on attempt {attempt + 1}: {e}")
            continue
            
    # If the loop finishes all 3 tries and still fails, default to our safe backup script.
    return ScriptResponse(
        questions=FALLBACK_SCRIPT,
        rationale="Generative agent failed strict validation. Defaulting to pre-programmed screening script.",
        fallback_used=True,
        retries=max_retries
    )

# A simple endpoint to check if the server is awake and running
@app.get("/health")
async def health_check():
    return {"status": "healthy"}