#!/bin/bash
# TWB - Tribal Wars Bot
# Activate virtual environment (Linux/Mac)

if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "✅ Virtual environment (.venv) activated."
elif [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Virtual environment (venv) activated."
elif [ -d "env" ]; then
    source env/bin/activate
    echo "✅ Virtual environment (env) activated."
else
    echo "❌ No virtual environment found. Run: python -m venv .venv"
    exit 1
fi
