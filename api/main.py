from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# --- Enable CORS so the Next.js frontend can call the API ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # allow requests from your web app
    allow_credentials=True,
    allow_methods=["*"],  # allow all HTTP methods
    allow_headers=["*"],  # allow all headers
)

# Request model for categorize endpoint
class CategorizeBody(BaseModel):
    description: str
    amount: float

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/categorize")
def categorize(body: CategorizeBody):
    """
    Dummy categorize endpoint — replace with AI logic later.
    """
    return {
        "merchant": None,
        "category": "Groceries",
        "is_subscription": False,
        "confidence": 0.5,
        "notes": ""
    }
