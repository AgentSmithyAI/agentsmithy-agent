#!/usr/bin/env python3
"""Test script to reproduce the explain streaming issue."""

import asyncio
import json
import aiohttp


async def test_explain_streaming():
    """Test explain with streaming - reproducing the issue."""
    print("🔄 Testing explain with streaming...")
    
    url = "http://localhost:11434/api/chat"
    data = {
        "messages": [
            {"role": "user", "content": "explain the code"}
        ],
        "context": {},  # No context, same as in the logs
        "stream": True
    }
    
    print(f"📤 Sending request: {json.dumps(data, indent=2)}")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=30)) as response:
            print(f"📡 Response status: {response.status}")
            print(f"📡 Response headers: {dict(response.headers)}")
            print(f"📡 Content-Type: {response.headers.get('Content-Type')}")
            
            # Check if response is SSE
            content_type = response.headers.get('Content-Type', '')
            if 'text/event-stream' not in content_type:
                print(f"⚠️  WARNING: Expected 'text/event-stream' but got '{content_type}'")
                # Try to read as regular response
                try:
                    body = await response.text()
                    print(f"📄 Response body: {body}")
                except Exception as e:
                    print(f"❌ Error reading response body: {e}")
                return
            
            print("\n📥 Streaming response:")
            line_count = 0
            chunk_count = 0
            
            async for line in response.content:
                line_count += 1
                line_str = line.decode('utf-8')
                
                # Print raw line with escape sequences visible
                print(f"[DEBUG #{line_count}] Raw: {repr(line_str)}")
                
                stripped = line_str.strip()
                if stripped:
                    print(f"[DEBUG #{line_count}] Stripped: '{stripped}'")
                    
                    if stripped.startswith('data: '):
                        data_str = stripped[6:]
                        
                        # Try to parse as JSON first
                        try:
                            data_json = json.loads(data_str)
                            print(f"[DEBUG] Parsed JSON: {data_json}")
                            
                            if 'content' in data_json:
                                chunk_count += 1
                                print(f"💬 Content chunk #{chunk_count}: {data_json['content']}")
                            elif 'type' in data_json:
                                print(f"🏷️  Event type: {data_json['type']}, task_type: {data_json.get('task_type')}")
                            elif 'done' in data_json:
                                print(f"✅ Done: {data_json['done']}")
                            elif 'error' in data_json:
                                print(f"❌ Error: {data_json['error']}")
                        except json.JSONDecodeError:
                            # Not JSON, treat as plain text content
                            chunk_count += 1
                            print(data_str, end='', flush=True)  # Print without newline
            
            print(f"\n📊 Summary: {line_count} lines received, {chunk_count} content chunks")


async def main():
    """Run the test."""
    print("🧪 Testing Explain Agent Streaming Issue")
    print("=" * 40)
    
    try:
        await test_explain_streaming()
    except aiohttp.ClientConnectorError:
        print("❌ Could not connect to server at http://localhost:11434")
    except asyncio.TimeoutError:
        print("❌ Request timed out after 30 seconds")
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main()) 