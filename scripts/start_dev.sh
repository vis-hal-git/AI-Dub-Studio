#!/usr/bin/env bash
# ─────────────────────────────────────────────
# Start development server
# ─────────────────────────────────────────────
set -e

echo "🎬 Video Dubbing Platform — Dev Server"
echo "════════════════════════════════════════"

# Check for .env
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Copying from .env.example..."
    cp .env.example .env
    echo "   Edit .env and add your OPENAI_API_KEY, then run again."
    exit 1
fi

# Load env
export $(grep -v '^#' .env | xargs)

if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "sk-your-openai-api-key-here" ]; then
    echo "❌ OPENAI_API_KEY not set in .env"
    exit 1
fi

echo "✅ OpenAI API key configured"
echo ""
echo "📡 Starting API on http://localhost:8000"
echo "📖 Docs at http://localhost:8000/docs"
echo ""

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
