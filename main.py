#!/usr/bin/env python3
"""Main entry point for AgentSmithy server."""

import sys
import os
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    # Check if .env file exists
    if not os.path.exists(".env"):
        print("⚠️  Warning: .env file not found!")
        print("Please create a .env file based on .env.example and add your OpenAI API key.")
        print("\nExample:")
        print("  cp .env.example .env")
        print("  # Edit .env and add your OPENAI_API_KEY")
        sys.exit(1)
    
    try:
        from agentsmithy_server.api.server import app, settings
        import uvicorn
        
        print("🚀 Starting AgentSmithy Server...")
        print(f"📍 Server will be available at http://{settings.server_host}:{settings.server_port}")
        print("📝 API documentation: http://localhost:11434/docs")
        print("\nPress Ctrl+C to stop the server")
        
        uvicorn.run(
            "agentsmithy_server.api.server:app",
            host=settings.server_host,
            port=settings.server_port,
            reload=True,
            log_level="info"
        )
    except ImportError as e:
        print(f"❌ Error importing required modules: {e}")
        print("\nPlease make sure you have installed all dependencies:")
        print("  pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1) 