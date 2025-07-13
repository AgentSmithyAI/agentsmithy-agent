#!/usr/bin/env python3
"""Test script with code context for explain agent."""

import asyncio
import json
import aiohttp


async def test_explain_with_context():
    """Test explain with code context."""
    print("🔄 Testing explain with code context...")
    
    url = "http://localhost:11434/api/chat"
    data = {
        "messages": [
            {"role": "user", "content": "explain this function"}
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
        "stream": True
    }
    
    print(f"📤 Sending request with code context")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=30)) as response:
            print(f"📡 Response status: {response.status}")
            
            line_count = 0
            chunk_count = 0
            full_response = []
            
            async for line in response.content:
                line_count += 1
                line_str = line.decode('utf-8').strip()
                
                if line_str and line_str.startswith('data: '):
                    data_str = line_str[6:]
                    try:
                        data_json = json.loads(data_str)
                        
                        if isinstance(data_json, dict):
                            if 'type' in data_json:
                                print(f"\n🏷️  Event: {data_json}")
                            elif 'done' in data_json:
                                print(f"\n✅ Done: {data_json['done']}")
                            elif 'error' in data_json:
                                print(f"\n❌ Error: {data_json['error']}")
                        else:
                            # JSON parsed to non-dict (shouldn't happen)
                            chunk_count += 1
                            print(f"💬 Chunk #{chunk_count}: {data_json}", end='', flush=True)
                            full_response.append(str(data_json))
                    except json.JSONDecodeError:
                        # Not JSON, treat as plain text
                        chunk_count += 1
                        print(data_str, end='', flush=True)
                        full_response.append(data_str)
            
            print(f"\n\n📊 Summary: {line_count} lines, {chunk_count} chunks")
            if full_response:
                print("\n📄 Full response:")
                print(''.join(full_response))


async def main():
    """Run the test."""
    print("🧪 Testing Explain Agent with Context")
    print("=" * 40)
    
    try:
        await test_explain_with_context()
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main()) 