"""Job360 FastAPI entrypoint.

Run from the backend/ directory:
    uvicorn main:app --reload
    python -m uvicorn main:app --host 0.0.0.0 --port 8000

The actual app wiring (routes, middleware, lifespan) lives in
src/api/main.py. This file exists as the canonical module path
that uvicorn and deployment platforms import.
"""
from src.api.main import app

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
