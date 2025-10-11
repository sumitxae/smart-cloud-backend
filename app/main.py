from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import time
from .api import auth, projects, deployments, cloud
from .database import engine, Base

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart Cloud Deploy API",
    description="Backend API for automated cloud deployments",
    version="1.0.0"
)

# Custom middleware to add request timeouts and isolation
@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    # Set different timeouts for different endpoints
    timeout_seconds = 30  # Default timeout
    
    if "/status" in str(request.url):
        timeout_seconds = 10  # Shorter timeout for status checks
    elif "/logs" in str(request.url) and "/stream" not in str(request.url):
        timeout_seconds = 10  # Shorter timeout for log fetches
    elif "/stream" in str(request.url):
        timeout_seconds = 300  # Longer timeout for streaming
    
    start_time = time.time()
    
    try:
        # Execute request with timeout
        response = await asyncio.wait_for(
            call_next(request), 
            timeout=timeout_seconds
        )
        
        # Add processing time header
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        return response
        
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=408,
            content={
                "detail": f"Request timed out after {timeout_seconds} seconds",
                "timeout": timeout_seconds,
                "path": str(request.url.path)
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Internal server error: {str(e)}",
                "path": str(request.url.path)
            }
        )

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(deployments.router, prefix="/api/v1/deployments", tags=["deployments"])
app.include_router(cloud.router, prefix="/api/v1/cloud", tags=["cloud"])

@app.get("/")
async def root():
    return {"message": "Smart Cloud Deploy API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}