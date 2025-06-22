#!/bin/bash

# Steam Trade Auto-Accepter - Build Script with .env file support

# Check if .env file exists and load it
if [ -f ".env" ]; then
    echo "📄 Loading configuration from .env file..."
    export $(grep -v '^#' .env | xargs)
else
    echo "⚠️  No .env file found. Using environment variables or defaults."
fi

# Check if required environment variables are set
if [ -z "$EMAIL_USERNAME" ] || [ -z "$EMAIL_PASSWORD" ]; then
    echo "❌ Error: Required environment variables not set!"
    echo ""
    echo "Option 1: Create a .env file with your credentials:"
    echo "  cp .env.example .env"
    echo "  # Edit .env with your actual values"
    echo ""
    echo "Option 2: Set environment variables manually:"
    echo "  export EMAIL_USERNAME=\"your-email@gmail.com\""
    echo "  export EMAIL_PASSWORD=\"your-app-password\""
    echo ""
    echo "Then run this script again."
    exit 1
fi

# Set default values for optional variables
EMAIL_SERVER=${EMAIL_SERVER:-"imap.gmail.com"}
ALLOWED_TRADERS=${ALLOWED_TRADERS:-"/id/buxy_xyz,steamcommunity.com/id/buxy_xyz"}
CHECK_INTERVAL=${CHECK_INTERVAL:-"300"}

echo "🚀 Building Steam Trade Auto-Accepter container..."
echo "📧 Email: $EMAIL_USERNAME"
echo "🛡️ Allowed traders: $ALLOWED_TRADERS"
echo "⏰ Check interval: $CHECK_INTERVAL seconds"
echo ""

# Check if the container exists
if docker ps -a --format '{{.Names}}' | grep -q '^gmail-trade-auto-accept$'; then
    echo "🛑 Stopping and removing existing container..."
    docker stop gmail-trade-auto-accept
    docker rm gmail-trade-auto-accept
fi

# Build the Docker image
echo "🔨 Building Docker image..."
docker build -t gmail-trade-auto-accept .

if [ $? -ne 0 ]; then
    echo "❌ Docker build failed!"
    exit 1
fi

# Run the Docker container with environment variables
echo "🐳 Starting container..."
docker run --name gmail-trade-auto-accept -d \
    --restart unless-stopped \
    -e TZ=Europe/Berlin \
    -e EMAIL_SERVER="$EMAIL_SERVER" \
    -e EMAIL_USERNAME="$EMAIL_USERNAME" \
    -e EMAIL_PASSWORD="$EMAIL_PASSWORD" \
    -e ALLOWED_TRADERS="$ALLOWED_TRADERS" \
    -e CHECK_INTERVAL="$CHECK_INTERVAL" \
    gmail-trade-auto-accept

if [ $? -eq 0 ]; then
    echo "✅ Container 'gmail-trade-auto-accept' started successfully!"
    echo ""
    echo "📋 Useful commands:"
    echo "  View logs:      docker logs -f gmail-trade-auto-accept"
    echo "  Stop container: docker stop gmail-trade-auto-accept"
    echo "  Restart:        docker restart gmail-trade-auto-accept"
    echo "  Remove:         docker rm gmail-trade-auto-accept"
    echo ""
    echo "🔍 Checking container status..."
    docker ps | grep gmail-trade-auto-accept
else
    echo "❌ Failed to start container!"
    exit 1
fi