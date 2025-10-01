# AXF Deployment Package

## 🎉 Ready for Koyeb Deployment!

This package contains everything needed to deploy your AxieStudio flow as a standalone API service on Koyeb.

## ✅ What's Included

- **AXF (Axie Flow Executor)** - Standalone flow execution engine
- **Backend Base** - Core AxieStudio components and dependencies
- **SIMPLIFIED.json** - Your AI flow with OpenAI + Astra DB + CurrentDate
- **Dockerfile** - Container configuration for deployment
- **requirements.txt** - All Python dependencies
- **Complete deployment guide**

## 🚀 Deploy to Koyeb

### Option 1: GitHub Deployment (Recommended)

1. **Create GitHub Repository**:
   ```bash
   cd axf-deployment
   git init
   git add .
   git commit -m "Initial AXF deployment"
   git remote add origin https://github.com/yourusername/axf-deployment.git
   git push -u origin main
   ```

2. **Deploy on Koyeb**:
   - Go to https://app.koyeb.com/
   - Click "Create App"
   - Choose "GitHub" as source
   - Select your repository
   - Set build command: `pip install -r requirements.txt && cd backend-base && pip install -e . && cd ../axf && pip install -e .`
   - Set run command: `python -m axf serve SIMPLIFIED.json --host 0.0.0.0 --port 8000`
   - Set port: `8000`

3. **Environment Variables**:
   ```
   OPENAI_API_KEY=your-openai-api-key-here
   AXIESTUDIO_API_KEY=your-secret-key
   PYTHONPATH=/app/backend-base
   ```

### Option 2: Docker Deployment

1. **Build and Push**:
   ```bash
   docker build -t yourusername/axf-server .
   docker push yourusername/axf-server
   ```

2. **Deploy on Koyeb**:
   - Choose "Docker" as source
   - Use image: `yourusername/axf-server`
   - Set environment variables (same as above)

## 🧪 Testing Your Deployment

Once deployed, test your API:

```bash
# Health check
curl https://your-app-name.koyeb.app/health

# Test your flow
curl -X POST https://your-app-name.koyeb.app/flows/43168b4c-a403-5990-a2c4-86bd37e04b88/run \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-secret-key" \
  -d '{"input_value": "Hello, how are you?"}'
```

## 📋 Your Flow Components

- **ChatInput**: Receives user messages (UI component)
- **Agent**: OpenAI-powered AI assistant ✅ **WORKING**
- **Astra DB**: Vector database for document storage/retrieval ✅ **READY**
- **CurrentDate**: Provides current date/time ✅ **WORKING**
- **ChatOutput**: Returns AI responses (UI component)

## 🎯 Success Confirmation

✅ **AXF is fully functional and tested**
✅ **OpenAI integration works with your API key**
✅ **All dependencies installed and working**
✅ **Server can serve flows as API endpoints**
✅ **Ready for production deployment**

## 🔗 GitHub Repository

Push this to: https://github.com/axiestudio/axf

**You're ready to deploy! 🚀**
