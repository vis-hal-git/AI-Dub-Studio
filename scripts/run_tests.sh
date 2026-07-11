#!/usr/bin/env bash
# ─────────────────────────────────────────────
# Run automated tests
# ─────────────────────────────────────────────
set -e

echo "🎬 Video Dubbing Platform — Test Runner"
echo "════════════════════════════════════════"

# Check for .env
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Copying from .env.example..."
    cp .env.example .env
    echo "   Edit .env and add your OPENAI_API_KEY"
fi

# Install dependencies if needed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

echo ""
echo "🧪 Running unit tests..."
python -m pytest tests/ -v --tb=short --asyncio-mode=auto

echo ""
echo "✅ All tests passed!"
