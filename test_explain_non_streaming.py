#!/usr/bin/env python3
"""Test explain agent in non-streaming mode."""

import asyncio
import json
import aiohttp


async def test_explain_non_streaming():
    """Test explain without streaming."""
    print("🔄 Testing explain in non-streaming mode...")
    
    url = "http://localhost:11434/api/chat"
    data = {
        "messages": [
            {"role": "user", "content": "explain the fibonacci function"}
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
        "stream": False  # Non-streaming mode
    }
    
    print(f"📤 Sending non-streaming request")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=30)) as response:
            print(f"📡 Response status: {response.status}")
            print(f"📡 Content-Type: {response.headers.get('Content-Type')}")
            
            result = await response.json()
            
            print("\n📄 Response JSON:")
            print(json.dumps(result, indent=2))
            
            if 'content' in result:
                print(f"\n💬 Content length: {len(result['content'])} chars")
                print("\n📝 First 500 chars of content:")
                print(result['content'][:500] + "..." if len(result['content']) > 500 else result['content'])
            
            if 'metadata' in result:
                print(f"\n📊 Metadata: {result['metadata']}")


async def main():
    """Run the test."""
    print("🧪 Testing Explain Agent (Non-Streaming)")
    print("=" * 40)
    
    try:
        await test_explain_non_streaming()
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main()) 