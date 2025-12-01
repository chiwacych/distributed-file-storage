# Quick Start Guide

## 🚀 Get Started in 5 Minutes

### Step 1: Prerequisites Check
```powershell
# Check Docker is installed
docker --version

# Check Docker Compose is installed
docker-compose --version
```

### Step 2: Start the System
```powershell
# Navigate to project directory
cd minio-dfs-project

# Start all services
docker-compose up -d

# Check all services are running
docker-compose ps
```

Expected output:
```
NAME                COMMAND                  STATUS              PORTS
fastapi-dfs         "uvicorn main:app..."   Up (healthy)        0.0.0.0:8000->8000/tcp
minio1              "minio server /data"     Up (healthy)        0.0.0.0:9000-9001->9000-9001/tcp
minio2              "minio server /data"     Up (healthy)        0.0.0.0:9010->9000/tcp, 0.0.0.0:9002->9002/tcp
minio3              "minio server /data"     Up (healthy)        0.0.0.0:9020->9000/tcp, 0.0.0.0:9003->9003/tcp
postgres-dfs        "docker-entrypoint..."  Up (healthy)        0.0.0.0:5432->5432/tcp
redis-cache         "redis-server..."        Up (healthy)        0.0.0.0:6379->6379/tcp
```

### Step 3: Access the Application

Open your browser and navigate to:
```
http://localhost:8000
```

You should see the Distributed File Storage System dashboard!

### Step 4: Upload Your First File

1. Click on "Select File" in the upload section
2. Choose any file from your computer
3. Enter a user ID (e.g., "user001")
4. Click "Upload to Distributed System"
5. Watch the file get replicated across all 3 MinIO nodes!

### Step 5: Verify Fault Tolerance

**Test Node Failure:**
```powershell
# Stop one MinIO node
docker stop minio2

# Go to the web UI and refresh the node health status
# You should see minio2 as "unhealthy"

# Try downloading a file - it should still work!

# Restart the node
docker start minio2
```

---

## 📱 Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| Web UI | http://localhost:8000 | None required |
| API Docs | http://localhost:8000/docs | None required |
| MinIO Console 1 | http://localhost:9001 | minioadmin / minioadmin123 |
| MinIO Console 2 | http://localhost:9002 | minioadmin / minioadmin123 |
| MinIO Console 3 | http://localhost:9003 | minioadmin / minioadmin123 |
| PostgreSQL | localhost:5432 | dfsuser / dfspassword |
| Redis | localhost:6379 | No password |

---

## 🔍 Quick Commands

### View Logs
```powershell
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f fastapi
docker-compose logs -f minio1
docker-compose logs -f postgres
```

### Restart Services
```powershell
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart fastapi
```

### Stop Everything
```powershell
# Stop all services
docker-compose down

# Stop and remove all data
docker-compose down -v
```

### Check Service Health
```powershell
# PowerShell
Invoke-WebRequest -Uri http://localhost:8000/api/nodes/health | ConvertFrom-Json

# Or use browser
http://localhost:8000/api/nodes/health
```

---

## ✅ Verification Checklist

- [ ] All 6 containers are running
- [ ] Web UI loads at http://localhost:8000
- [ ] Can upload a file successfully
- [ ] File appears in the file list
- [ ] All 3 MinIO nodes show as healthy
- [ ] Can download uploaded file
- [ ] Statistics panel shows data

---

## 🐛 Quick Troubleshooting

### Services won't start
```powershell
docker-compose down -v
docker-compose up -d --build
```

### Port already in use
Edit `docker-compose.yml` and change the port mappings:
```yaml
ports:
  - "8001:8000"  # Change 8000 to 8001
```

### Can't access web UI
1. Check firewall settings
2. Try http://127.0.0.1:8000
3. Check logs: `docker-compose logs fastapi`

---

## 🎯 Next Steps

1. ✅ Upload multiple files
2. ✅ Test fault tolerance (stop a node)
3. ✅ Check replication status
4. ✅ View system statistics
5. ✅ Test concurrent uploads
6. ✅ Verify cache performance

---

## 📚 Learn More

- Full documentation: See README.md
- API documentation: http://localhost:8000/docs
- MinIO documentation: https://min.io/docs

---

**Need help?** Check the troubleshooting section in README.md
