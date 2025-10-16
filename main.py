from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, replicate_ai

app = FastAPI(title="FastAPI x Replicate")

# Development CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth routes
app.include_router(auth.router, prefix="/auth")

# Routes "AI"
app.include_router(replicate_ai.router, prefix="/ai", tags=["ai"])

@app.get("/")
def root():
    return {"ok": True}
