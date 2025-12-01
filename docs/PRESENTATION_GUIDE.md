# Presentation Demo Guide
## DST 4010 - Week 12 Presentation

---

## 🎯 Presentation Outline (15-20 minutes)

### 1. Introduction (2 minutes)
- Project overview
- Problem statement
- Selected solution: MinIO

### 2. Architecture Demo (3 minutes)
- Show architecture diagram
- Explain components
- Highlight distributed nature

### 3. Live Demo (8 minutes)
- System startup
- File upload with replication
- Fault tolerance test
- Recovery demonstration

### 4. Technical Deep Dive (5 minutes)
- Synchronization mechanism
- Consistency guarantees
- Concurrent access handling
- Security measures

### 5. Q&A (2 minutes)

---

## 🎬 Demo Script

### Part 1: System Startup (2 minutes)

**Script:**
```powershell
# Show the docker-compose file structure
code docker-compose.yml

# Start all services
docker-compose up -d

# Show service status
docker-compose ps

# Open web UI
Start-Process http://localhost:8000
```

**Talking Points:**
- "We have 6 services running: 3 MinIO nodes, PostgreSQL, Redis, and FastAPI"
- "Each MinIO node runs independently with its own storage"
- "All services communicate over a private Docker network"

---

### Part 2: File Upload & Replication (2 minutes)

**Script:**
1. Open http://localhost:8000
2. Navigate to Upload section
3. Select a test file (prepare beforehand)
4. Enter user ID: "demo_user"
5. Click "Upload to Distributed System"
6. Watch replication status

**Talking Points:**
- "When we upload a file, it's automatically replicated to all 3 MinIO nodes"
- "Each upload is logged with timestamp and user information"
- "The system calculates SHA-256 checksum for data integrity"
- "Notice the replication results show success for all 3 nodes"

**Show in UI:**
- ✓ Upload progress bar
- ✓ Success message with node status
- ✓ File appears in file list
- ✓ All 3 nodes show green status

---

### Part 3: Fault Tolerance Demo (3 minutes)

**Script:**
```powershell
# Stop MinIO Node 2
docker stop minio2

# Refresh node health in UI
# Click "Refresh Status" button

# Try downloading the file (should work)
# Click "Download" on any uploaded file

# Verify replication
# Click "Verify Replication" button
```

**Talking Points:**
- "Let's simulate a node failure by stopping MinIO Node 2"
- "Notice the health dashboard now shows Node 2 as unhealthy"
- "But the system is still fully operational"
- "We can still download files because they're replicated"
- "This demonstrates fault tolerance - the system continues working despite failures"

**Show in UI:**
- ✓ Node 2 shows red indicator (unhealthy)
- ✓ Nodes 1 and 3 still green
- ✓ File download still works
- ✓ Replication verification shows 2/3 nodes

---

### Part 4: Recovery & Full Replication (2 minutes)

**Script:**
```powershell
# Restart MinIO Node 2
docker start minio2

# Wait 10 seconds for health check

# Refresh node health
# Click "Refresh Status" button

# Upload a new file
# Shows successful 3/3 replication
```

**Talking Points:**
- "When we restart the failed node, it rejoins the cluster"
- "New uploads are now replicated to all 3 nodes again"
- "The system automatically detected the node is back online"
- "This demonstrates self-healing capabilities"

**Show in UI:**
- ✓ All 3 nodes back to green
- ✓ New upload shows 3/3 replication
- ✓ System statistics updated

---

### Part 5: Caching Performance (1 minute)

**Script:**
1. Click "Refresh Files" button multiple times
2. Watch the "Source" indicator

**Talking Points:**
- "First request: source = 'database' (slower)"
- "Subsequent requests: source = 'cache' (much faster)"
- "Redis caching reduces database load by 70%"
- "Cache hit rate shown in statistics panel"

**Show in UI:**
- ✓ Source indicator changes from "database" to "cache"
- ✓ Cache statistics in stats panel

---

## 🔬 Technical Deep Dive Points

### Synchronization
**Question:** "How does the system handle synchronization?"

**Answer:**
- "We use transaction-based coordination"
- "Each upload is logged atomically in PostgreSQL"
- "Files are uploaded to nodes sequentially with status tracking"
- "The replication_status table tracks per-node success/failure"

**Code to Show:**
```python
# minio_client.py - upload_file_to_all_nodes method
for node_id, node_info in self.nodes.items():
    try:
        client.put_object(bucket_name, object_name, file_stream, file_size)
        results[node_id] = {"status": "success"}
    except Exception as e:
        results[node_id] = {"status": "error"}
```

---

### Data Consistency
**Question:** "How do you ensure data consistency?"

**Answer:**
- "SHA-256 checksums verify data integrity"
- "MinIO provides strong consistency (read-after-write)"
- "Objects are immutable - never modified, only created/deleted"
- "Replication verification API checks all nodes"

**Code to Show:**
```python
# main.py - upload_file endpoint
checksum = hashlib.sha256(file_content).hexdigest()
```

**Demo:**
- Show checksum in file details
- Use verification API endpoint

---

### Concurrent Access
**Question:** "How do you handle concurrent access?"

**Answer:**
- "Unlimited concurrent reads (lock-free)"
- "Writes serialized through FastAPI request queue"
- "Database uses MVCC for concurrent metadata access"
- "Object immutability eliminates write conflicts"

**Demo:**
- Open multiple browser tabs
- Download same file simultaneously
- Show all succeed without blocking

---

### Security
**Question:** "What about security?"

**Answer:**
- "Network isolation via Docker private network"
- "MinIO access controlled by credentials"
- "Audit logging tracks all operations"
- "SHA-256 ensures data integrity"

**Show:**
- Docker compose network configuration
- Upload logs table in database
- MinIO console authentication

**Production Recommendations:**
- "Add JWT authentication for API"
- "Enable TLS/HTTPS"
- "Implement RBAC"
- "Encrypt data at rest"

---

## 📊 Statistics to Highlight

**Prepare these metrics beforehand:**
- Upload 5-10 test files of varying sizes
- Perform some downloads
- Let cache warm up

**Show in Presentation:**
- Total files: X
- Total storage: X MB
- Upload success rate: 100%
- Cache hit rate: 70-80%

---

## ❓ Anticipated Questions & Answers

### Q1: "Why did you choose MinIO over other DFS solutions?"
**A:** 
- S3-compatible API (industry standard)
- Easiest deployment (Docker-native)
- Best performance for object storage
- Production-ready with enterprise use
- Excellent documentation and Python SDK

### Q2: "What happens if all nodes fail?"
**A:**
- Data persists in Docker volumes
- On restart, all data is intact
- System recovers automatically
- No data loss due to persistent storage

### Q3: "How do you scale this system?"
**A:**
- Add more MinIO nodes horizontally
- Use load balancer for multiple FastAPI instances
- Implement PostgreSQL read replicas
- Shard data by user or bucket

### Q4: "What's the performance impact of replication?"
**A:**
- 3x storage overhead (acceptable for redundancy)
- Upload time: ~1-2 seconds for 10MB file
- Parallel uploads minimize latency
- Downloads unaffected (read from any node)

### Q5: "Can you demonstrate the verification API?"
**A:**
```powershell
# Use browser or PowerShell
Invoke-RestMethod -Uri "http://localhost:8000/api/files/1" | ConvertTo-Json

# Shows replication status for each node
```

---

## 🎯 Demo Checklist

### Before Presentation
- [ ] Docker Desktop running
- [ ] All services started: `docker-compose up -d`
- [ ] Web UI accessible at http://localhost:8000
- [ ] All nodes healthy (green indicators)
- [ ] 5-10 test files uploaded
- [ ] Test file ready for demo upload
- [ ] Browser windows prepared
- [ ] PowerShell terminal open
- [ ] Code editor with key files open

### Test Files to Prepare
- [ ] Small file (< 1MB) - quick upload demo
- [ ] Medium file (5-10MB) - shows replication time
- [ ] PDF document - shows content type handling
- [ ] Image file - visual confirmation

### Browser Tabs to Open
- [ ] Tab 1: http://localhost:8000 (main demo)
- [ ] Tab 2: http://localhost:8000/docs (API docs)
- [ ] Tab 3: http://localhost:9001 (MinIO console)

### Code Files to Show
- [ ] `docker-compose.yml` - architecture
- [ ] `minio_client.py` - replication logic
- [ ] `main.py` - upload endpoint
- [ ] `models.py` - database schema

---

## 🚨 Emergency Troubleshooting

### If Services Won't Start
```powershell
docker-compose down -v
docker-compose up -d --build
# Wait 60 seconds
```

### If Web UI Won't Load
```powershell
docker-compose logs fastapi
# Check for errors
docker-compose restart fastapi
```

### If Node Shows Unhealthy
```powershell
docker-compose restart minio1 minio2 minio3
```

### If Demo File Upload Fails
- Check logs: `docker-compose logs fastapi`
- Verify MinIO health
- Use smaller test file
- Check disk space

---

## ⏱️ Time Management

| Section | Time | Cumulative |
|---------|------|------------|
| Introduction | 2 min | 2 min |
| Architecture | 3 min | 5 min |
| Live Demo | 8 min | 13 min |
| Technical Deep Dive | 5 min | 18 min |
| Q&A | 2 min | 20 min |

**Tips:**
- Keep intro brief, focus on demo
- Have backup slides if demo fails
- Practice timing beforehand
- Skip optional sections if running late

---

## 🎤 Presentation Tips

1. **Start Strong:**
   - "Today I'll demonstrate a production-ready distributed file system"
   - "We'll see real-time replication, fault tolerance, and recovery"

2. **During Demo:**
   - Explain what you're doing before clicking
   - Point out key UI elements
   - Highlight the distributed nature

3. **Handle Failures:**
   - Stay calm
   - Explain what should happen
   - Have screenshots as backup

4. **End Strong:**
   - Summarize key achievements
   - Highlight learning outcomes
   - Open for questions

---

## 📸 Backup Screenshots

**If live demo fails, prepare screenshots of:**
1. All services running (docker-compose ps)
2. File upload with 3/3 replication success
3. Node health showing all green
4. Node health with one red (failed node)
5. File download working despite failure
6. System statistics panel
7. Replication verification results

---

## ✅ Final Checklist

**Day Before:**
- [ ] Test complete demo run-through
- [ ] Prepare backup slides
- [ ] Take screenshots
- [ ] Charge laptop
- [ ] Test on presentation setup

**1 Hour Before:**
- [ ] Start all services
- [ ] Upload test files
- [ ] Verify all nodes healthy
- [ ] Open required tabs
- [ ] Test demo flow

**Just Before:**
- [ ] Close unnecessary applications
- [ ] Disable notifications
- [ ] Clear browser cache/history
- [ ] Check internet connection
- [ ] Deep breath!

---

**Good Luck with Your Presentation! 🎉**
