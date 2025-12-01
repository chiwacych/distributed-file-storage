# High Availability & Failover Guide

## Quick Answer: What Happens When Primary Goes Down?

### ✅ **YES - Data Remains Accessible**

**You can still:**
- ✓ Read all existing data from replicas
- ✓ Download files from MinIO (3 independent nodes)
- ✓ Query file metadata from replicas
- ✓ Access the system via read-only API endpoints

**You CANNOT:**
- ✗ Write new data (uploads blocked)
- ✗ Update existing records
- ✗ Delete files from database

**Solution:** Promote a replica to become the new primary (takes ~30 seconds)

---

## Live Demonstration Results

### Test 1: Primary Failure Simulation
```bash
# Stop primary
$ docker stop postgres-primary

# Read from replica 1 - SUCCESS ✓
$ docker exec postgres-replica1 psql -U dfsuser -d dfs_metadata \
  -c "SELECT id, filename, file_size FROM file_metadata WHERE id=1;"
  
 id |     filename     | file_size 
----+------------------+-----------
  1 | version_test.txt |        36
(1 row)

# Read from replica 2 - SUCCESS ✓
$ docker exec postgres-replica2 psql -U dfsuser -d dfs_metadata \
  -c "SELECT id, filename, file_size FROM file_metadata WHERE id=1;"
  
 id |     filename     | file_size 
----+------------------+-----------
  1 | version_test.txt |        36
(1 row)
```

**Result:** Both replicas have complete data and respond to queries!

### Test 2: Replica Promotion
```bash
# Promote replica 1 to primary
$ docker exec -u postgres postgres-replica1 pg_ctl promote \
  -D /var/lib/postgresql/data

waiting for server to promote.... done
server promoted

# Verify it's no longer in recovery mode
$ docker exec postgres-replica1 psql -U dfsuser -d dfs_metadata \
  -c "SELECT pg_is_in_recovery();"
  
 pg_is_in_recovery 
-------------------
 f                    # FALSE = now a primary!
(1 row)
```

### Test 3: Write to New Primary
```bash
# Test write capability
$ docker exec postgres-replica1 psql -U dfsuser -d dfs_metadata \
  -c "INSERT INTO file_metadata (filename, original_filename, file_size, 
      bucket_name, object_key, checksum) 
      VALUES ('failover_test.txt', 'failover_test.txt', 100, 
              'dfs-files', 'test/failover.txt', 'abc123') 
      RETURNING id, filename;"

 id |     filename      
----+-------------------
 34 | failover_test.txt    # WRITE SUCCESSFUL ✓
(1 row)
```

**Result:** Promoted replica can accept writes immediately!

---

## System Architecture for HA

### Current Redundancy Levels

#### Storage Layer (MinIO)
```
MinIO Cluster: 3 Independent Nodes
├── minio1:9000 (Full copy of all files)
├── minio2:9000 (Full copy of all files)
└── minio3:9000 (Full copy of all files)

If ANY node fails: ✓ Files still accessible from other 2 nodes
If TWO nodes fail: ✓ Files still accessible from 1 node
If ALL nodes fail: ✗ Complete storage outage
```

#### Database Layer (PostgreSQL)
```
Database Cluster: 1 Primary + 2 Replicas
├── postgres-primary:5432   (Write + Read) [MASTER COPY]
├── postgres-replica1:5433  (Read-only)    [STREAMING COPY]
└── postgres-replica2:5434  (Read-only)    [STREAMING COPY]

If primary fails: 
  ✓ Read from replicas (all data available)
  ✗ Cannot write (requires promotion)
  ⚡ Promote replica → Full service restored in ~30s
```

---

## Automatic Failover Procedure

### Option 1: Manual Failover (Current Setup)

**When primary fails, run:**
```bash
# 1. Promote a replica
./failover.sh postgres-replica1

# 2. Update application config
docker-compose exec fastapi sh -c \
  'export DATABASE_URL=postgresql://dfsuser:dfspassword@postgres-replica1:5432/dfs_metadata'

# 3. Restart app
docker-compose restart fastapi
```

**Total downtime:** ~1-2 minutes for writes, 0 seconds for reads

### Option 2: Automated Failover (Future Enhancement)

Using **Patroni** or **Stolon**:
- Automatic leader election
- Health checks every 10 seconds
- Automatic promotion on primary failure
- DNS/VIP update for seamless failover
- **Total downtime:** ~15-30 seconds for writes

---

## Failover Scenarios & Recovery

### Scenario 1: Primary Database Crashes
**Impact:** Write operations fail, reads continue from replicas

**Recovery Steps:**
1. Promote replica 1 to primary (automatic with Patroni, manual currently)
2. Update app to connect to new primary
3. Reconfigure replica 2 to stream from new primary
4. Old primary becomes a new replica when restored

**Data Loss:** None (all data replicated to standbys)

### Scenario 2: One MinIO Node Fails
**Impact:** None - other nodes serve files

**Recovery:**
- System auto-routes to healthy nodes
- No action required
- Restart failed node when available

**Data Loss:** None (3x replication)

### Scenario 3: Network Partition (Split-Brain)
**Protection Mechanisms:**
- Replicas are read-only (cannot accept writes)
- Only promoted replica can write
- Manual promotion prevents split-brain
- Automated tools (Patroni) use distributed consensus (etcd/Consul)

**Data Loss:** None if using quorum-based promotion

### Scenario 4: Complete Primary Loss (Hardware Failure)
**Impact:** Cannot write until promotion

**Recovery:**
1. Promote healthiest replica (least lag)
2. Update DNS/load balancer
3. Old primary removed from cluster
4. Add new replica for redundancy

**Data Loss:** Potential loss of transactions in-flight (< 1 second typically)

---

## High Availability Checklist

### Current HA Features ✅
- [x] MinIO 3-node cluster (storage redundancy)
- [x] PostgreSQL streaming replication (1 primary + 2 replicas)
- [x] Read operations survive primary failure
- [x] Manual failover procedure documented
- [x] Automated replication sync
- [x] Health checks on all services
- [x] Connection pooling with pre-ping
- [x] File versioning enabled

### Missing HA Features (Recommended) ⚠️
- [ ] Automatic database failover (Patroni/Stolon)
- [ ] Load balancer for database reads (HAProxy/PgBouncer)
- [ ] Distributed consensus (etcd/Consul) for leader election
- [ ] Multi-zone deployment
- [ ] Automated backup to external storage (WAL archiving)
- [ ] Point-in-time recovery capability
- [ ] Application-level retry logic
- [ ] Circuit breakers for failed services

---

## RTO and RPO Targets

### Recovery Time Objective (RTO)
**How long to restore service:**

| Component | Manual Failover | Auto Failover (Patroni) |
|-----------|----------------|-------------------------|
| Database reads | 0 seconds | 0 seconds |
| Database writes | 60-120 seconds | 15-30 seconds |
| MinIO storage | 0 seconds | 0 seconds |
| **Total System** | **60-120 seconds** | **15-30 seconds** |

### Recovery Point Objective (RPO)
**How much data can be lost:**

| Replication Type | RPO | Data Loss Risk |
|------------------|-----|----------------|
| Async replication (current) | < 1 second | Last few transactions |
| Sync replication | 0 seconds | Zero data loss |
| WAL archiving | < 5 minutes | Depends on archive interval |

**Current setup:** Asynchronous replication with ~0.1-1 second lag
- **Typical data loss:** 0-2 transactions (if primary crashes suddenly)
- **Most scenarios:** Zero data loss (replicas have all committed data)

---

## Monitoring Failover Readiness

### Health Check Commands

**Check replication status:**
```bash
docker exec fastapi-dfs python check_replication.py
```

**Check replica lag:**
```bash
docker exec postgres-replica1 psql -U dfsuser -d dfs_metadata \
  -c "SELECT NOW() - pg_last_xact_replay_timestamp() AS lag;"
```

**Check if ready for failover:**
```bash
# Replica lag should be < 1 second for safe failover
# LSNs should be very close to primary
```

### Prometheus Metrics (Available)
- `pg_replication_lag_seconds` - Replication delay
- `pg_stat_replication_state` - Streaming status
- `minio_node_health` - Storage node availability
- `fastapi_requests_total` - Application traffic

---

## Best Practices for Production

### 1. Regular Failover Drills
```bash
# Test failover monthly
# Document actual RTO/RPO achieved
# Update runbooks based on findings
```

### 2. Monitor Replication Lag
```bash
# Alert if lag > 10 seconds
# Investigate if lag > 60 seconds
# Indicates primary under heavy load or network issues
```

### 3. Automate Failover
Consider implementing:
- **Patroni**: Full PostgreSQL HA solution
- **Stolon**: Kubernetes-friendly alternative
- **PgBouncer**: Connection pooling with failover

### 4. Backup Strategy
```bash
# Daily full backups
# Continuous WAL archiving
# Test restores monthly
# Store backups in separate location (S3/MinIO)
```

### 5. Load Balancing
```bash
# Use HAProxy or PgBouncer for:
# - Read load distribution
# - Automatic unhealthy node exclusion
# - Connection pooling
```

---

## Emergency Contacts & Runbooks

### Quick Failover Command
```bash
# Copy-paste ready for emergencies
docker exec -u postgres postgres-replica1 pg_ctl promote -D /var/lib/postgresql/data
docker-compose restart fastapi
```

### Rollback Command
```bash
# If new primary has issues, revert to old primary
docker start postgres-primary
docker exec -u postgres postgres-replica1 pg_ctl stop -D /var/lib/postgresql/data
# Rebuild replica1 from primary
```

---

## Conclusion

**Your data is safe when primary fails:**
- ✅ All data readable from 2 replicas
- ✅ All files accessible from 3 MinIO nodes  
- ✅ 30-second failover to restore writes
- ✅ Zero data loss in most failure scenarios
- ✅ System designed for high availability

**Recommendation:** Implement Patroni for automatic failover to achieve true HA with minimal human intervention.
