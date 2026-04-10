#!/usr/bin/env python3
"""KakaoChat AI Server entry point."""
import uvicorn

from app.config import load_config

if __name__ == "__main__":
    cfg = load_config()
    server = cfg["server"]
    uvicorn.run(
        "app.main:app",
        host=server["host"],
        port=server["port"],
        reload=True,
    )
