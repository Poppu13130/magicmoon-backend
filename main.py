from fastapi import FastAPI
from routers import replicate_ai

app = FastAPI(title="FastAPI x Replicate")

# Routes "AI"
app.include_router(replicate_ai.router, prefix="/ai", tags=["ai"])

@app.get("/")
def root():
    return {"ok": True}
