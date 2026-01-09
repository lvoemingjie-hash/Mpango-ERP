#!/bin/bash
# Mpango ERP Setup Script

echo "🚀 Setting up Mpango ERP..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs
mkdir -p uploads

# Copy environment files if they don't exist
if [ ! -f backend/.env ]; then
    echo "📝 Creating backend .env file..."
    cp backend/.env.example backend/.env
fi

if [ ! -f frontend/.env ]; then
    echo "📝 Creating frontend .env file..."
    echo "VITE_API_URL=http://localhost:8000/api/v1" > frontend/.env
fi

# Start services
echo "🐳 Starting Docker services..."
docker-compose up -d postgres redis

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
sleep 10

# Install backend dependencies and run migrations
echo "🔧 Setting up backend..."
cd backend
pip install -r requirements.txt

# Run Alembic migrations for default tenant
echo "🗄️ Running database migrations..."
alembic upgrade head -x tenant_schema=t_dev

cd ..

# Install frontend dependencies
echo "🎨 Setting up frontend..."
cd frontend
npm install
cd ..

echo "✅ Setup complete!"
echo ""
echo "To start the development servers:"
echo "1. Backend: cd backend && uvicorn main:app --reload"
echo "2. Frontend: cd frontend && npm run dev"
echo ""
echo "Or use Docker Compose:"
echo "docker-compose up backend frontend"