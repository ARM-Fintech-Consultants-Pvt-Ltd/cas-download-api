from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Header, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
from datetime import datetime
from pdf_parser import CASParser
import shutil
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables with defaults
PORT = int(os.getenv("PORT", 8080))
API_KEY = os.getenv("API_KEY")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 10))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", 60))
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080,http://localhost:3000").split(",")

app = FastAPI(
    title="CAS Parser API",
    description="API for parsing CAMS and NSDL CAS PDFs",
    version="1.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create temp directory
TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Simple API key validation
async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key

# Rate limiting
request_counts = {}

async def check_rate_limit(request: Request):
    if not RATE_LIMIT_PER_MINUTE:
        return
        
    client_ip = request.client.host
    current_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    key = f"{client_ip}:{current_minute}"
    count = request_counts.get(key, 0)
    
    if count >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
    request_counts[key] = count + 1

@app.post("/parse/cas")
async def parse_cas(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(...),
    output_format: str = Form(default="json"),
    x_api_key: Optional[str] = Header(None)
):
    """
    Parse a CAS PDF file and return the data in JSON or Excel format
    """
    # Verify API key if configured
    await verify_api_key(x_api_key)
    
    # Check rate limit
    await check_rate_limit(request)
    
    temp_path = None
    try:
        # Validate file
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
            
        # Validate output format
        if output_format.lower() not in ['json', 'excel']:
            raise HTTPException(status_code=400, detail="Output format must be 'json' or 'excel'")
            
        # Validate file size
        file_content = await file.read()
        if len(file_content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"File size must be less than {MAX_FILE_SIZE_MB}MB")
            
        # Save uploaded file temporarily
        temp_path = os.path.join(TEMP_DIR, f"{datetime.now().timestamp()}_{file.filename}")
        with open(temp_path, "wb") as buffer:
            buffer.write(file_content)
        
        try:
            # Parse the CAS PDF
            parser = CASParser(temp_path, password)
            cas_data = parser.parse()
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to parse PDF: {str(e)}. Please check if the password is correct and the file is a valid CAS PDF."
            )
        
        if output_format.lower() == 'json':
            # Return JSON response
            result = {
                "meta": cas_data.meta.__dict__,
                "investor_info": cas_data.investor_info.__dict__,
                "mutual_funds": [mf.__dict__ for mf in cas_data.mutual_funds],
                "portfolio_summary": cas_data.portfolio_summary.__dict__
            }
            
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return JSONResponse(content=result)
        else:
            # Return Excel file
            excel_path = os.path.join(TEMP_DIR, f"{datetime.now().timestamp()}_output.xlsx")
            try:
                parser.to_excel(excel_path)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to generate Excel file: {str(e)}"
                )
                
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
            response = FileResponse(
                excel_path,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename="cas_data.xlsx"
            )
            return response
            
    except HTTPException as he:
        # Re-raise HTTP exceptions
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        raise he
    except Exception as e:
        # Handle unexpected errors
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )

@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
