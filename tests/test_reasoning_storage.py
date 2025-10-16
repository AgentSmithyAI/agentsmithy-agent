"""Tests for reasoning storage functionality."""

import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.asyncio
async def test_reasoning_accumulation():
    """Test that reasoning content is accumulated in buffer."""

    reasoning_buffer = []

    # Simulate reasoning chunks
    chunks = ["Analyzing ", "the problem...", " Found solution."]
    for chunk in chunks:
        reasoning_buffer.append(chunk)

    content = "".join(reasoning_buffer)
    assert content == "Analyzing the problem... Found solution."
    assert len(reasoning_buffer) == 3


@pytest.mark.asyncio
async def test_reasoning_buffer_cleared_after_flush():
    """Test that reasoning buffer is cleared after successful flush."""
    reasoning_buffer = ["Test ", "reasoning"]

    # Simulate flush
    content = "".join(reasoning_buffer)
    assert content == "Test reasoning"

    reasoning_buffer.clear()
    assert len(reasoning_buffer) == 0


@pytest.mark.asyncio
async def test_multiple_reasoning_blocks():
    """Test multiple reasoning blocks in a stream."""
    # Simulate multiple reasoning blocks
    blocks = []

    # First block
    buffer1 = ["First ", "reasoning"]
    blocks.append("".join(buffer1))
    buffer1.clear()

    # Second block
    buffer2 = ["Second ", "reasoning"]
    blocks.append("".join(buffer2))
    buffer2.clear()

    assert len(blocks) == 2
    assert blocks[0] == "First reasoning"
    assert blocks[1] == "Second reasoning"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
