from fastapi import FastAPI
from controllers.screenshots_controller import router as screenshots_router

app = FastAPI(title="Screenshot Runner")

@app.get("/health")
def health():
    return {"status": "ok"}

# mount endpoints
app.include_router(screenshots_router)

