from fastapi import FastAPI

app = FastAPI(
    title="AirAware API",
    description="AI-powered urban air quality assistant",
    version="1.0.0",
)


@app.get("/")
def home():
    return {
        "message": "Welcome to AirAware!",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}