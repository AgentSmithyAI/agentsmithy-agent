#!/usr/bin/env python3
"""Test client for AgentSmithy server."""

import asyncio
import json
import aiohttp
from typing import AsyncIterator


async def test_streaming_request():
    """Test SSE streaming request."""
    print("🔄 Testing streaming request...")
    
    url = "http://localhost:11434/api/chat"
    data = {
        "messages": [
            {"role": "user", "content": "Help me refactor this function to be more efficient"}
        ],
        "context": {
            "current_file": {
                "path": "example.py",
                "language": "python",
                "content": """def calculate_sum(numbers):
    total = 0
    for i in range(len(numbers)):
        total = total + numbers[i]
    return total""",
                "selection": ""
            }
        },
        "stream": True
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            print(f"📡 Response status: {response.status}")
            print(f"📡 Response headers: {dict(response.headers)}")  # Added debug
            
            line_count = 0  # Added debug
            async for line in response.content:
                line_count += 1  # Added debug
                line_str = line.decode('utf-8').strip()
                print(f"[DEBUG] Line #{line_count}: '{line_str}'")  # Added debug
                
                if line_str.startswith('data: '):
                    data_str = line_str[6:]  # Remove 'data: ' prefix
                    print(f"[DEBUG] Stripped: '{data_str}'")  # Added debug
                    
                    if data_str and data_str != '[DONE]':
                        try:
                            data_json = json.loads(data_str)
                            print(f"[DEBUG] Parsed JSON: {data_json}")  # Added debug
                            
                            if 'content' in data_json:
                                print(data_json['content'], end='', flush=True)
                            elif 'type' in data_json:
                                print(f"\n🏷️  Task classified as: {data_json.get('task_type', 'unknown')}")
                            elif 'done' in data_json and data_json['done']:
                                print("\n✅ Stream completed")
                            elif 'error' in data_json:
                                print(f"\n❌ Error: {data_json['error']}")
                        except json.JSONDecodeError:
                            # Not JSON, treat as plain text content
                            print(data_str, end='', flush=True)
            
            print(f"[DEBUG] Total lines received: {line_count}")  # Added debug
    print("\n")


async def test_regular_request():
    """Test regular non-streaming request."""
    print("🔄 Testing regular request...")
    
    url = "http://localhost:11434/api/chat"
    data = {
        "messages": [
            {"role": "user", "content": "What is the purpose of this function?"}
        ],
        "context": {
            "current_file": {
                "path": "example.py",
                "language": "python",
                "content": """def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)"""
            }
        },
        "stream": False
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            print(f"📡 Response status: {response.status}")
            result = await response.json()
            print(f"📝 Response: {result.get('content', 'No content')}")
            print(f"📊 Metadata: {result.get('metadata', {})}")
    print("\n")


async def test_health_check():
    """Test health check endpoint."""
    print("🔄 Testing health check...")
    
    url = "http://localhost:11434/health"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            print(f"📡 Response status: {response.status}")
            result = await response.json()
            print(f"💚 Health status: {result}")
    print("\n")


async def main():
    """Run all tests."""
    print("🧪 AgentSmithy Server Test Client")
    print("================================\n")
    
    # Test health check
    await test_health_check()
    
    # Test regular request
    await test_regular_request()
    
    # Test streaming request
    await test_streaming_request()
    
    print("✅ All tests completed!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except aiohttp.ClientConnectorError:
        print("❌ Could not connect to server. Make sure the server is running on http://localhost:11434")
    except KeyboardInterrupt:
        print("\n👋 Test interrupted by user") 