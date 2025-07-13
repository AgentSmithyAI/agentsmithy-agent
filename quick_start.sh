#!/bin/bash

echo "🚀 AgentSmithy Quick Start"
echo "========================"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  Creating .env file from template..."
    cp .env.example .env
    echo "❗ Please edit .env and add your OPENAI_API_KEY"
    echo "   Press Enter to continue after adding the key..."
    read
fi

# Start the server
echo "🚀 Starting AgentSmithy server..."
python main.py 