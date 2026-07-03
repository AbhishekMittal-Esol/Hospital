import uvicorn
from backend.main import app

if __name__ == "__main__":
    print("Starting Uvicorn on port 5000...")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=5000, log_level="info", reload=True)
