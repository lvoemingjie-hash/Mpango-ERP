#!/bin/bash
# Development startup script

echo "🚀 Starting Mpango ERP development environment..."

# Start database and Redis
echo "🐳 Starting database services..."
docker-compose up -d postgres redis

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 5

# Start backend in background
echo "🔧 Starting backend server..."
cd backend
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
cd ..

# Start frontend in background  
echo "🎨 Starting frontend server..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo "✅ Development servers started!"
echo "📊 Backend API: http://localhost:8000"
echo "🌐 Frontend: http://localhost:5173"
echo "📚 API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all servers"

# Wait for interrupt signal
trap 'echo "🛑 Stopping servers..."; kill $BACKEND_PID $FRONTEND_PID; docker-compose stop; exit' INT
wait