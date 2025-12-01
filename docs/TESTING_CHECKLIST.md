# Testing Checklist
## Pre-Presentation Verification

---

## ⚙️ System Setup Tests

### Docker Environment
- [ ] Docker Desktop is running
- [ ] Docker version: `docker --version`
- [ ] Docker Compose version: `docker-compose --version`
- [ ] No port conflicts (8000, 5432, 6379, 9000-9003, 9010, 9020)

### Service Startup
- [ ] Run: `docker-compose up -d`
- [ ] Wait 60 seconds for health checks
- [ ] Verify all 6 containers running: `docker-compose ps`
- [ ] All show status: "Up (healthy)"

**Expected Output:**
```
NAME                COMMAND                  STATUS
fastapi-dfs         "uvicorn main:app..."   Up (healthy)
minio1              "minio server /data"     Up (healthy)
minio2              "minio server /data"     Up (healthy)
minio3              "minio server /data"     Up (healthy)
postgres-dfs        "docker-entrypoint..."  Up (healthy)
redis-cache         "redis-server..."        Up (healthy)
```

---

## 🌐 Web Interface Tests

### UI Accessibility
- [ ] Open: http://localhost:8000
- [ ] Page loads without errors
- [ ] Header shows: "Distributed File Storage System"
- [ ] All sections visible:
  - [ ] Upload File
  - [ ] MinIO Cluster Status
  - [ ] System Statistics
  - [ ] Uploaded Files

### Initial State
- [ ] Node Health shows 3 nodes
- [ ] All nodes show green indicators
- [ ] Statistics show initial values
- [ ] File list is empty or shows previous files

---

## 📤 Upload Functionality Tests

### Test 1: Basic Upload
- [ ] Click "Select File"
- [ ] Choose a small file (< 1MB)
- [ ] Enter User ID: "test_user"
- [ ] Click "Upload to Distributed System"
- [ ] Success alert appears
- [ ] Message shows "3/3 nodes"
- [ ] File appears in file list
- [ ] Statistics updated

**Record:**
- File name: ________________
- File size: ________________
- Upload time: ______________

### Test 2: Upload with Description
- [ ] Upload another file
- [ ] Add description: "Test file for demo"
- [ ] Verify description appears in file details

### Test 3: Multiple Uploads
- [ ] Upload 3-5 different files
- [ ] Verify all appear in file list
- [ ] Check statistics show correct total

**Files uploaded:**
1. ________________ (______ KB)
2. ________________ (______ KB)
3. ________________ (______ KB)
4. ________________ (______ KB)
5. ________________ (______ KB)

---

## 📥 Download Functionality Tests

### Test 4: File Download
- [ ] Click "Download" on any file
- [ ] File downloads successfully
- [ ] File opens correctly
- [ ] Download alert appears

### Test 5: Multiple Downloads
- [ ] Download same file 3 times
- [ ] All downloads successful
- [ ] No errors or timeouts

---

## 🔍 Verification Tests

### Test 6: File Details
- [ ] Click "Details" on a file
- [ ] Alert shows file information
- [ ] Checksum is displayed
- [ ] Source is shown (cache/database)

### Test 7: Replication Verification
- [ ] Click "Verify Replication" on a file
- [ ] Verification completes
- [ ] Shows status for all 3 nodes
- [ ] All nodes show "✓ Found"

---

## 📊 Statistics Tests

### Test 8: Statistics Panel
- [ ] Click "Refresh Stats"
- [ ] Total Files: _____ (correct count)
- [ ] Total Storage: _____ MB
- [ ] Upload Success Rate: _____ %
- [ ] Cache Hit Rate: _____ %

### Test 9: Node Health
- [ ] Click "Refresh Status" in Node Health
- [ ] All 3 nodes update
- [ ] All show healthy status
- [ ] Endpoints displayed correctly

---

## 🚨 Fault Tolerance Tests

### Test 10: Single Node Failure
```powershell
# Stop Node 2
docker stop minio2
```

- [ ] Command executed successfully
- [ ] Wait 10 seconds
- [ ] Click "Refresh Status" in UI
- [ ] minio2 shows as unhealthy (red indicator)
- [ ] minio1 and minio3 still healthy (green)
- [ ] Try downloading a file
- [ ] Download works successfully
- [ ] Try uploading a new file
- [ ] Upload succeeds (shows 2/3 replication)

**Record:**
- Download after failure: [ ] Success / [ ] Fail
- Upload after failure: [ ] Success / [ ] Fail
- Nodes replicated: _____ / 3

### Test 11: Node Recovery
```powershell
# Restart Node 2
docker start minio2
```

- [ ] Command executed successfully
- [ ] Wait 15 seconds for health check
- [ ] Click "Refresh Status"
- [ ] minio2 shows as healthy again
- [ ] All 3 nodes green
- [ ] Upload new file
- [ ] Shows 3/3 replication

**Recovery time:** _____ seconds

### Test 12: Two Node Failure (Optional)
```powershell
docker stop minio2 minio3
```

- [ ] Both nodes stopped
- [ ] UI shows 2 unhealthy nodes
- [ ] Download still works
- [ ] Upload shows 1/3 success

```powershell
# Recovery
docker start minio2 minio3
```

---

## 💾 Cache Performance Tests

### Test 13: Cache Hit
- [ ] Click "Refresh Files"
- [ ] Note source: "database" (first time)
- [ ] Click "Refresh Files" again
- [ ] Note source: "cache" (second time)
- [ ] Response faster on second request

### Test 14: Cache Invalidation
- [ ] Upload a new file
- [ ] File list updates automatically
- [ ] Click "Refresh Files"
- [ ] New file appears in list

---

## 🔄 Concurrent Access Tests

### Test 15: Simultaneous Downloads
- [ ] Open 3 browser tabs: http://localhost:8000
- [ ] In each tab, download the same file
- [ ] All downloads succeed
- [ ] No errors or slowdowns

### Test 16: Simultaneous Uploads
- [ ] In 2 different tabs
- [ ] Upload different files at same time
- [ ] Both uploads succeed
- [ ] Both files appear in list

---

## 🗑️ Delete Functionality Tests

### Test 17: File Deletion
- [ ] Click "Delete" on a file
- [ ] Confirmation dialog appears
- [ ] Click "OK"
- [ ] Success message appears
- [ ] File removed from list
- [ ] Statistics updated

### Test 18: Verify Deletion from All Nodes
After deleting a file:
- [ ] File removed from minio1
- [ ] File removed from minio2
- [ ] File removed from minio3

(Can verify via MinIO console)

---

## 🔌 API Tests

### Test 19: API Documentation
- [ ] Open: http://localhost:8000/docs
- [ ] Swagger UI loads
- [ ] All endpoints visible:
  - [ ] POST /api/upload
  - [ ] GET /api/files
  - [ ] GET /api/files/{file_id}
  - [ ] GET /api/files/{file_id}/download
  - [ ] DELETE /api/files/{file_id}
  - [ ] GET /api/nodes/health
  - [ ] GET /api/stats
  - [ ] GET /api/replication/verify/{file_id}

### Test 20: Direct API Call (PowerShell)
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/files" | ConvertTo-Json
```

- [ ] Command executes successfully
- [ ] Returns JSON with file list
- [ ] Shows "status": "success"
- [ ] Shows "source": "cache" or "database"

---

## 🎨 MinIO Console Tests

### Test 21: MinIO Console Access
- [ ] Open: http://localhost:9001
- [ ] Login page appears
- [ ] Enter: minioadmin / minioadmin123
- [ ] Dashboard loads
- [ ] "dfs-files" bucket exists
- [ ] Files visible in bucket

### Test 22: File Verification in MinIO
- [ ] Navigate to dfs-files bucket
- [ ] See uploaded files
- [ ] Check file sizes match
- [ ] Verify on all 3 nodes (ports 9001, 9002, 9003)

---

## 🗄️ Database Tests

### Test 23: Database Connection (Optional)
```powershell
docker exec -it postgres-dfs psql -U dfsuser -d dfs_metadata
```

SQL queries:
```sql
-- Check tables exist
\dt

-- Count files
SELECT COUNT(*) FROM file_metadata WHERE is_deleted = false;

-- Check upload logs
SELECT * FROM upload_logs ORDER BY upload_timestamp DESC LIMIT 5;

-- Check replication status
SELECT * FROM replication_status;

-- Exit
\q
```

- [ ] Database accessible
- [ ] All 4 tables exist
- [ ] Data matches UI

---

## 📱 Redis Cache Tests

### Test 24: Redis Connection (Optional)
```powershell
docker exec -it redis-cache redis-cli
```

Redis commands:
```redis
# Check cached keys
KEYS *

# Get cache stats
INFO stats

# Check specific key
GET "files:list:all"

# Exit
exit
```

- [ ] Redis accessible
- [ ] Cache keys exist
- [ ] Stats show hits/misses

---

## ⏱️ Performance Benchmarks

### Test 25: Upload Speed
Upload files and record times:

| File Size | Upload Time | Speed |
|-----------|-------------|-------|
| 1 MB      | _____ ms    | _____ MB/s |
| 5 MB      | _____ ms    | _____ MB/s |
| 10 MB     | _____ s     | _____ MB/s |

### Test 26: Download Speed
Download files and record times:

| File Size | Download Time | Speed |
|-----------|---------------|-------|
| 1 MB      | _____ ms      | _____ MB/s |
| 5 MB      | _____ ms      | _____ MB/s |
| 10 MB     | _____ s       | _____ MB/s |

### Test 27: Cache Performance
- First file list load: _____ ms (database)
- Second file list load: _____ ms (cache)
- Performance improvement: _____ %

---

## 🔐 Security Tests

### Test 28: Network Isolation
- [ ] Try accessing MinIO from external tool (should work)
- [ ] Try accessing PostgreSQL externally (should work on port 5432)
- [ ] Services communicate internally

### Test 29: Authentication
- [ ] MinIO console requires login
- [ ] Wrong password rejected
- [ ] Correct password accepted

---

## 🐛 Error Handling Tests

### Test 30: Invalid File Upload
- [ ] Try uploading without selecting file
- [ ] Error message appears
- [ ] System remains stable

### Test 31: Network Error Simulation
- [ ] Disconnect from internet (if applicable)
- [ ] Upload should still work (local Docker)
- [ ] All operations function normally

### Test 32: Service Restart
```powershell
docker-compose restart fastapi
```

- [ ] Service restarts successfully
- [ ] UI reconnects
- [ ] Data persists
- [ ] All functions work

---

## 📋 Final Verification

### System Health
- [ ] All 6 containers running
- [ ] All services healthy
- [ ] No errors in logs: `docker-compose logs`
- [ ] Web UI fully functional
- [ ] All 3 MinIO nodes operational

### Data Integrity
- [ ] All uploaded files downloadable
- [ ] Checksums match
- [ ] Metadata accurate
- [ ] Replication verified

### Performance
- [ ] Upload success rate: _____ %
- [ ] Cache hit rate: _____ %
- [ ] Average upload time: _____ s
- [ ] Average download time: _____ s

### Documentation
- [ ] README.md complete
- [ ] QUICKSTART.md tested
- [ ] PROJECT_REPORT.md reviewed
- [ ] PRESENTATION_GUIDE.md prepared

---

## 🎯 Pre-Presentation Final Checks

### 24 Hours Before
- [ ] Run complete test suite
- [ ] Document any issues
- [ ] Prepare backup plan
- [ ] Take screenshots

### 1 Hour Before
- [ ] Restart all services
- [ ] Upload fresh test files
- [ ] Verify all functionality
- [ ] Clear browser cache

### Just Before Presentation
- [ ] All services running
- [ ] All nodes healthy
- [ ] Test file ready
- [ ] Browser tabs prepared
- [ ] Backup materials ready

---

## ✅ Sign-Off

**Tester:** ______________________  
**Date:** ________________________  
**Time:** ________________________

**All Critical Tests Passed:** [ ] Yes / [ ] No

**Issues Found:**
1. _________________________________
2. _________________________________
3. _________________________________

**Resolution:**
1. _________________________________
2. _________________________________
3. _________________________________

**System Ready for Presentation:** [ ] Yes / [ ] No

**Notes:**
_____________________________________________
_____________________________________________
_____________________________________________

---

## 🚨 Emergency Contacts

**If something goes wrong:**

1. Check logs: `docker-compose logs`
2. Restart services: `docker-compose restart`
3. Full reset: `docker-compose down -v && docker-compose up -d`
4. Review QUICKSTART.md troubleshooting
5. Use backup screenshots/video

---

**Testing Complete! System Ready! 🎉**
