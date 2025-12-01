# PostgreSQL Replication Guide

## Overview
The distributed file storage system uses PostgreSQL streaming replication with 1 primary and 2 read replicas for high availability and read scalability.

## Architecture

### Database Topology
```
Primary (postgres-primary:5432)
├── Replica 1 (postgres-replica1:5433)
└── Replica 2 (postgres-replica2:5434)
```

### Replication Features
- **Streaming Replication**: Asynchronous WAL streaming from primary to replicas
- **Read Replicas**: Both replicas accept read-only connections
- **Load Balancing**: Random selection of replicas for read operations
- **Auto-Failover**: Manual failover support (can be automated with tools like Patroni)
- **Connection Pooling**: Each database has its own connection pool (5 connections + 10 overflow)

## Configuration

### Primary Database
The primary database is configured to:
- Enable WAL archiving (`wal_level = replica`)
- Support up to 10 WAL sender processes
- Allow replication connections from any IP
- Create dedicated `replicator` user for streaming

**Configuration** (`postgres-config/primary-init.sh`):
```bash
# WAL settings
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
hot_standby = on
archive_mode = on

# Replication user
CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'replicator123';
```

### Replica Databases
Replicas are initialized using base backup from primary and configured for hot standby mode.

**Configuration** (`postgres-config/replica-init.sh`):
```bash
# Create base backup from primary
pg_basebackup -h postgres-primary -D ${PGDATA} -U replicator -v -P -W -R

# Enable hot standby
hot_standby = on
```

## Application Usage

### Write Operations (Primary Only)
All data modifications go to the primary database:

```python
from database import get_db

@app.post("/api/upload")
async def upload_file(db: Session = Depends(get_db)):
    # Uses primary database for writes
    file_record = FileMetadata(...)
    db.add(file_record)
    db.commit()
```

### Read Operations (Replicas)
Read queries can use replicas for better performance:

```python
from database import get_read_db

@app.get("/api/files")
async def list_files(db: Session = Depends(get_read_db)):
    # Uses random replica (or primary if no replicas)
    files = db.query(FileMetadata).all()
    return files
```

### Load Balancing
The `get_read_db()` function randomly selects a replica for each request:

```python
def get_read_db() -> Generator[Session, None, None]:
    if replica_session_makers:
        # Random selection from available replicas
        session_maker = random.choice(replica_session_makers)
        db = session_maker()
    else:
        # Fallback to primary
        db = SessionLocal()
    
    try:
        yield db
    finally:
        db.close()
```

## Monitoring Replication

### Using the Monitoring Script
```bash
# Run from within FastAPI container
docker exec fastapi-dfs python check_replication.py
```

**Output Example**:
```
PRIMARY DATABASE STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Active Replicas: 2

  Replica 1:
    Client: 172.18.0.12
    State: streaming
    Sync State: async

REPLICA 1 STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
In Recovery Mode: True
Replication Lag: 0:00:34.065085
Last Received LSN: 0/40838C8
Last Replayed LSN: 0/40838C8
```

### Using PostgreSQL Queries

**Check replication status on primary**:
```sql
SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn,
       sync_state, application_name
FROM pg_stat_replication;
```

**Check replica lag**:
```sql
-- On replica
SELECT NOW() - pg_last_xact_replay_timestamp() AS replication_lag;
```

**Check recovery mode**:
```sql
-- On replica (should return true)
SELECT pg_is_in_recovery();
```

## Port Mapping

| Service | Container Port | Host Port | Purpose |
|---------|----------------|-----------|---------|
| Primary | 5432 | 5432 | Write operations |
| Replica 1 | 5432 | 5433 | Read operations |
| Replica 2 | 5432 | 5434 | Read operations |
| Legacy postgres | 5432 | 5435 | Backward compatibility |

## Environment Variables

```bash
# Primary database connection
DATABASE_URL=postgresql://dfsuser:dfspassword@postgres-primary:5432/dfs_metadata

# Replica connections (optional - falls back to primary if not set)
DATABASE_REPLICA1_URL=postgresql://dfsuser:dfspassword@postgres-replica1:5432/dfs_metadata
DATABASE_REPLICA2_URL=postgresql://dfsuser:dfspassword@postgres-replica2:5432/dfs_metadata
```

## Replication Lag

### Expected Lag
- **Asynchronous replication**: 5-60 seconds typical lag
- **Factors affecting lag**:
  - Network latency between containers
  - Write transaction volume
  - Replica performance
  - WAL archiving speed

### Monitoring Lag
Use the monitoring script or query:
```sql
SELECT NOW() - pg_last_xact_replay_timestamp() AS lag;
```

## Failover Procedures

### Manual Failover (Primary Failure)

1. **Promote a replica to primary**:
```bash
# On replica container
docker exec -it postgres-replica1 bash
pg_ctl promote -D /var/lib/postgresql/data
```

2. **Update application configuration**:
```bash
# Change DATABASE_URL to point to new primary
DATABASE_URL=postgresql://dfsuser:dfspassword@postgres-replica1:5432/dfs_metadata
```

3. **Restart FastAPI**:
```bash
docker-compose restart fastapi
```

4. **Reconfigure remaining replica**:
```bash
# Update standby.signal and recovery settings
# Point to new primary
```

### Automated Failover (Future Enhancement)
Consider using:
- **Patroni**: Automatic failover and leader election
- **PgBouncer**: Connection pooling with failover support
- **Repmgr**: Replication management and monitoring

## Backup Strategy

### Continuous Archiving (WAL Archive)
Currently using `/bin/true` placeholder:
```bash
archive_command = '/bin/true'  # Replace with actual archiving
```

**Production recommendation**:
```bash
# Archive to S3/MinIO
archive_command = 'wal-g wal-push %p'
```

### Base Backups
```bash
# Create backup from primary
pg_basebackup -h postgres-primary -D /backup/$(date +%Y%m%d) \
              -U replicator -v -P -W
```

## Performance Tuning

### Connection Pooling
Each database has optimized pooling:
```python
pool_size=5           # Base connections
max_overflow=10       # Additional connections under load
pool_pre_ping=True    # Verify connections before use
```

### Read Scaling
- Distribute read queries across 2 replicas
- Random load balancing prevents hotspots
- Can add more replicas by duplicating config

### Write Performance
- All writes go to primary
- Consider upgrading primary resources if write-heavy
- Monitor `pg_stat_activity` for connection usage

## Troubleshooting

### Replica Not Streaming
```bash
# Check logs
docker logs postgres-replica1

# Verify primary allows replication
docker exec postgres-primary psql -U dfsuser -d dfs_metadata \
  -c "SELECT * FROM pg_hba.conf WHERE type='host' AND database='replication';"

# Check network connectivity
docker exec postgres-replica1 ping postgres-primary
```

### High Replication Lag
```bash
# Check WAL sender processes
docker exec postgres-primary psql -U dfsuser -d dfs_metadata \
  -c "SELECT * FROM pg_stat_replication;"

# Monitor WAL generation rate
docker exec postgres-primary psql -U dfsuser -d dfs_metadata \
  -c "SELECT pg_current_wal_lsn();"

# Check replica apply rate
docker exec postgres-replica1 psql -U dfsuser -d dfs_metadata \
  -c "SELECT pg_last_wal_replay_lsn();"
```

### Split-Brain Prevention
Replicas are read-only and cannot accept writes:
```sql
-- On replica (will fail)
INSERT INTO file_metadata VALUES (...);
-- ERROR:  cannot execute INSERT in a read-only transaction
```

## Best Practices

1. **Always use `get_db()` for writes**: Ensures data goes to primary
2. **Use `get_read_db()` for reads**: Distributes load across replicas
3. **Monitor replication lag**: Run monitoring script regularly
4. **Plan for failover**: Document and test failover procedures
5. **Backup regularly**: Implement WAL archiving to external storage
6. **Scale reads**: Add more replicas as read load increases
7. **Test recovery**: Periodically test replica promotion

## Future Enhancements

- [ ] Automated failover with Patroni or Stolon
- [ ] Synchronous replication option for critical data
- [ ] WAL archiving to MinIO/S3 for point-in-time recovery
- [ ] Connection pooler (PgBouncer) for better scaling
- [ ] Read replica auto-discovery
- [ ] Replication metrics in Prometheus
- [ ] Grafana dashboard for replication monitoring
