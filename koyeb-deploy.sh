#!/bin/bash

# AXF Koyeb Deployment Script
echo "🚀 Deploying AXF to Koyeb..."

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "📦 Initializing Git repository..."
    git init
    git add .
    git commit -m "Initial AXF deployment package"
fi

# Check if remote exists
if ! git remote get-url origin > /dev/null 2>&1; then
    echo "❌ Please add your GitHub repository as origin:"
    echo "git remote add origin https://github.com/yourusername/axf-deployment.git"
    exit 1
fi

# Push to GitHub
echo "📤 Pushing to GitHub..."
git add .
git commit -m "Update AXF deployment - $(date)"
git push origin main

echo "✅ Code pushed to GitHub!"
echo ""
echo "🎯 Next steps:"
echo "1. Go to https://app.koyeb.com/"
echo "2. Click 'Create App'"
echo "3. Choose 'GitHub' as source"
echo "4. Select your repository"
echo "5. Set build command: pip install -r requirements.txt && cd backend-base && pip install -e . && cd ../axf && pip install -e ."
echo "6. Set run command: python -m axf serve SIMPLIFIED.json --host 0.0.0.0 --port 8000"
echo "7. Set port: 8000"
echo "8. Add environment variables:"
echo "   - OPENAI_API_KEY=your-openai-api-key-here"
echo "   - AXIESTUDIO_API_KEY=your-secret-key"
echo "   - PYTHONPATH=/app/backend-base"
echo ""
echo "🎉 Your AXF deployment is ready!"
