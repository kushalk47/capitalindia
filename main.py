from fastapi import FastAPI, Depends, Request, HTTPException, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Dict, Union
from pydantic import BaseModel
import io
import base64
from PIL import Image # Import Pillow
import os # For environment variables
from datetime import datetime # For date handling

# --- IMPORTANT: For loading environment variables ---
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import models

# Import our chatbot service modules
from chatbot_service.parser import QueryParser
from chatbot_service.chatbot import GeminiChatbot

# Initialize the database on startup
models.initialize_database()

app = FastAPI()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global variable to store last image (for chat context) ---
# Stores PIL Image object for subsequent analysis requests
last_uploaded_image_pil = None 

# --- Gemini API Keys (Using environment variables is best practice) ---
# Collect all API keys from environment variables
GEMINI_API_KEYS = []
for i in range(1, 6): # Assuming you have GOOGLE_API_KEY_1 to GOOGLE_API_KEY_5
    key = os.getenv(f"GOOGLE_API_KEY_{i}")
    if key:
        GEMINI_API_KEYS.append(key)
    else:
        print(f"WARNING: GOOGLE_API_KEY_{i} environment variable not set.")

if not GEMINI_API_KEYS:
    raise ValueError("No Gemini API keys found in environment variables. Please set at least GOOGLE_API_KEY_1.")
else:
    print(f"Successfully loaded {len(GEMINI_API_KEYS)} Gemini API keys.")

# Initialize Gemini Chatbot once on app startup, passing the LIST of API keys
gemini_chatbot = GeminiChatbot(api_keys=GEMINI_API_KEYS) 

# Pydantic model for incoming chat messages
class ChatMessage(BaseModel):
    message: str

# Pydantic model for incoming chart analysis requests (for initial upload)
class ChartUploadRequest(BaseModel):
    image_data: str # Base64 encoded image string

# Dependency to get DB session
def get_db():
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API Endpoint to Serve Stock Data for Visualization ---
@app.get("/api/stock_data", response_model=List[Dict[str, Union[str, float, int, None]]])
async def get_stock_data_api(db: Session = Depends(get_db)):
    stock_records = db.query(models.StockData).order_by(models.StockData.timestamp).all()

    formatted_data = []
    for record in stock_records:
        formatted_data.append({
            "time": record.timestamp.isoformat(),
            "open": record.open_price,
            "high": record.high_price,
            "low": record.low_price,
            "close": record.close_price,
            "volume": record.volume,
            "direction": record.direction,
            "support_lower": record.support_lower,
            "support_upper": record.support_upper,
            "resistance_lower": record.resistance_lower,
            "resistance_upper": record.resistance_upper,
        })
    return formatted_data

# --- Combined API Endpoint for Chatbot Text and Contextual Image Analysis ---
@app.post("/api/chat")
async def chat_with_gemini_combined(message: ChatMessage, db: Session = Depends(get_db)):
    global last_uploaded_image_pil # Declare intent to modify global variable

    user_query = message.message
    user_query_lower = user_query.lower().strip()

    # Instantiate parser with the db session and the shared gemini_chatbot instance
    parser = QueryParser(db=db, gemini_chatbot=gemini_chatbot)
    
    response_content = "I'm not sure how to respond to that."
    
    # --- Check for explicit image analysis command ---
    # This is for when the user types "analyze chart" *after* an image has been uploaded
    if "analyze chart" in user_query_lower or "analyze image" in user_query_lower:
        if last_uploaded_image_pil:
            detailed_analysis_prompt = """
            Based on the provided stock chart image, conduct a technical analysis focusing on aspects relevant to traders:

            1.  **Overall Trend:** Describe the predominant trend (uptrend, downtrend, sideways/ranging) and its strength.
            2.  **Volatility:** Assess the level of volatility (high/low, stable/unstable) based on candle sizes.
            3.  **Key Candlestick Patterns:** Identify any classic bullish or bearish reversal/continuation candlestick patterns (e.g., Hammer, Shooting Star, Engulfing, Doji, Marubozu). Specify their approximate date/location if possible.
            4.  **Support and Resistance:** Identify visible horizontal support and resistance levels. Describe if the price is respecting them or breaking through. (Note: The bands are overlaid in your visualization, so Gemini should pick them up if it's processing the image as it appears visually).
            5.  **Volume Analysis (if visible):** Comment on the volume trend. Does it confirm price movements or show divergence? Are there any significant volume spikes?
            6.  **Directional Signal Markers (if visible and discernible):** Observe the green (LONG), red (SHORT), and yellow (None) markers. Do they appear to be placed effectively relative to price movements?

            Synthesize these observations into a concise summary suitable for a trader or investment banker, highlighting potential trading implications or key observations.
            """
            try:
                # Call Gemini Vision with the stored PIL image
                vision_response = gemini_chatbot.analyze_chart_image(
                    image=last_uploaded_image_pil,
                    user_query=detailed_analysis_prompt
                )
                return JSONResponse(content={"response": vision_response}) # Changed to return vision_response directly
            except Exception as e:
                print(f"Error during contextual image analysis: {e}")
                return JSONResponse(content={"response": f"Sorry, I had trouble analyzing the chart image: {e}"}, status_code=500)
        else:
            response_content = "Please upload an image first for me to analyze."
            return JSONResponse(content={"response": response_content})
    
    # --- Otherwise, attempt to handle as a database query or general text query ---
    parsed_result = parser.parse_and_execute(user_query)

    if parsed_result["type"] == "db_response":
        response_content = parsed_result["content"]
    else: # type == "gemini_response" (meaning Text-to-SQL failed or it's a general question)
        # If Text-to-SQL fails or it's a general question, ask Gemini directly for a conversational response
        gemini_response_text = gemini_chatbot.send_text_query(user_query)
        response_content = gemini_response_text
    
    return JSONResponse(content={"response": response_content})

# --- REVERTED: Original API Endpoint for Chart Image Upload & Analysis ---
# THIS IS THE ENDPOINT YOUR FRONTEND IS LIKELY HITTING for initial image upload
@app.post("/api/analyze_chart") # REVERTED back to original name
async def analyze_chart(request_body: ChartUploadRequest):
    global last_uploaded_image_pil # Declare intent to modify global variable

    try:
        # Decode the Base64 string to bytes
        image_bytes = base64.b64decode(request_body.image_data)
        # Open the image bytes using PIL (Pillow)
        image_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        
        # Store the PIL image globally for later contextual analysis
        last_uploaded_image_pil = image_pil

        # Initial prompt for immediate feedback
        initial_analysis_prompt = "Analyze this stock chart image for major trends and any obvious immediate patterns. Provide a brief overview."
        
        # Perform initial image analysis with a general prompt
        initial_analysis_response = gemini_chatbot.analyze_chart_image(
            image=image_pil,
            user_query=initial_analysis_prompt,
        )
        return JSONResponse(content={"response": f"Image received and here's a quick initial analysis:\n\n{initial_analysis_response}"})

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid image data: {e}")
    except Exception as e:
        print(f"Error during initial chart upload and analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Chart analysis failed: {e}")


# --- Frontend Routes ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    current_year = datetime.now().year
    return templates.TemplateResponse("dashboard.html", {"request": request, "title": "TSLA Stock Dashboard", "current_year": current_year})

@app.get("/chatbot", response_class=HTMLResponse)
async def read_chatbot_page(request: Request):
    current_year = datetime.now().year
    return templates.TemplateResponse("chatbot.html", {"request": request, "title": "TSLA Chatbot", "current_year": current_year})


# --- Run the FastAPI app (for development) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)