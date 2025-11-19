# Setup and Deployment Script for Windows PowerShell
# Distributed File Storage System

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Distributed File Storage System Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Docker
Write-Host "Checking Docker installation..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version
    Write-Host "✓ Docker found: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker not found. Please install Docker Desktop first." -ForegroundColor Red
    Write-Host "  Download from: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
    exit 1
}

# Check Docker Compose
Write-Host "Checking Docker Compose..." -ForegroundColor Yellow
try {
    $composeVersion = docker-compose --version
    Write-Host "✓ Docker Compose found: $composeVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker Compose not found." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Services..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Stop any existing containers
Write-Host "Stopping any existing containers..." -ForegroundColor Yellow
docker-compose down 2>$null

# Build and start services
Write-Host "Building and starting all services..." -ForegroundColor Yellow
docker-compose up -d --build

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Services started successfully!" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to start services." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Waiting for services to become healthy (this may take 30-60 seconds)..." -ForegroundColor Yellow

# Wait for services to be healthy
$maxWait = 60
$waited = 0
$healthy = $false

while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 5
    $waited += 5
    
    $status = docker-compose ps --format json 2>$null | ConvertFrom-Json
    $allHealthy = $true
    
    foreach ($service in $status) {
        if ($service.Health -and $service.Health -ne "healthy") {
            $allHealthy = $false
            break
        }
    }
    
    if ($allHealthy) {
        $healthy = $true
        break
    }
    
    Write-Host "  Still waiting... ($waited seconds)" -ForegroundColor Gray
}

Write-Host ""

if ($healthy) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "✓ All Services are Ready!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    
    # Display service status
    Write-Host "Service Status:" -ForegroundColor Cyan
    docker-compose ps
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Access Points" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Web UI:          http://localhost:8000" -ForegroundColor Yellow
    Write-Host "API Docs:        http://localhost:8000/docs" -ForegroundColor Yellow
    Write-Host "MinIO Console 1: http://localhost:9001" -ForegroundColor Yellow
    Write-Host "MinIO Console 2: http://localhost:9002" -ForegroundColor Yellow
    Write-Host "MinIO Console 3: http://localhost:9003" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "MinIO Credentials:" -ForegroundColor Cyan
    Write-Host "  Username: minioadmin" -ForegroundColor Gray
    Write-Host "  Password: minioadmin123" -ForegroundColor Gray
    Write-Host ""
    
    # Try to open browser
    Write-Host "Opening Web UI in browser..." -ForegroundColor Yellow
    Start-Process "http://localhost:8000"
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Quick Commands" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "View logs:        docker-compose logs -f" -ForegroundColor Gray
    Write-Host "Stop services:    docker-compose down" -ForegroundColor Gray
    Write-Host "Restart services: docker-compose restart" -ForegroundColor Gray
    Write-Host "Service status:   docker-compose ps" -ForegroundColor Gray
    Write-Host ""
    
    Write-Host "✓ Setup Complete! System is ready to use." -ForegroundColor Green
    
} else {
    Write-Host "⚠ Services started but may not be fully healthy yet." -ForegroundColor Yellow
    Write-Host "  Check status with: docker-compose ps" -ForegroundColor Gray
    Write-Host "  View logs with: docker-compose logs" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
