from fastapi import FastAPI
from routers import auth, replicate_ai

app = FastAPI(title="FastAPI x Replicate")

# Auth routes
app.include_router(auth.router, prefix="/auth")

# Routes "AI"
app.include_router(replicate_ai.router, prefix="/ai", tags=["ai"])

@app.get("/")
def root():
    return {"ok": True}
