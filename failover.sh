#!/bin/bash
# PostgreSQL Failover Script
# Promotes a replica to primary when primary fails

set -e

REPLICA_TO_PROMOTE=${1:-postgres-replica1}

echo "=============================================="
echo "PostgreSQL Failover Script"
echo "=============================================="
echo ""

# Check if primary is down
echo "Checking primary status..."
if docker exec postgres-primary pg_isready -U dfsuser 2>/dev/null; then
    echo "❌ ERROR: Primary is still running!"
    echo "   This script should only be used when primary is down."
    exit 1
fi

echo "✓ Primary is down, proceeding with failover"
echo ""

# Promote replica
echo "Promoting ${REPLICA_TO_PROMOTE} to primary..."
docker exec -u postgres ${REPLICA_TO_PROMOTE} pg_ctl promote -D /var/lib/postgresql/data

# Wait for promotion to complete
sleep 3

# Verify promotion
echo ""
echo "Verifying promotion..."
IS_RECOVERY=$(docker exec ${REPLICA_TO_PROMOTE} psql -U dfsuser -d dfs_metadata -t -c "SELECT pg_is_in_recovery();")

if [[ "$IS_RECOVERY" == *"f"* ]]; then
    echo "✓ ${REPLICA_TO_PROMOTE} successfully promoted to primary!"
else
    echo "❌ Promotion failed - database still in recovery mode"
    exit 1
fi

# Test write capability
echo ""
echo "Testing write capability..."
TEST_ID=$(docker exec ${REPLICA_TO_PROMOTE} psql -U dfsuser -d dfs_metadata -t -c \
    "INSERT INTO file_metadata (filename, original_filename, file_size, bucket_name, object_key, checksum) 
     VALUES ('failover_test_$(date +%s).txt', 'test', 1, 'dfs-files', 'test/$(date +%s)', 'test') 
     RETURNING id;")

if [ -n "$TEST_ID" ]; then
    echo "✓ Write test successful (record ID: ${TEST_ID})"
else
    echo "❌ Write test failed"
    exit 1
fi

echo ""
echo "=============================================="
echo "FAILOVER COMPLETED SUCCESSFULLY"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Update application DATABASE_URL to point to ${REPLICA_TO_PROMOTE}"
echo "   DATABASE_URL=postgresql://dfsuser:dfspassword@${REPLICA_TO_PROMOTE}:5432/dfs_metadata"
echo ""
echo "2. Restart FastAPI service:"
echo "   docker-compose restart fastapi"
echo ""
echo "3. Configure remaining replica to stream from new primary"
echo ""
echo "4. When old primary is restored:"
echo "   - Rebuild as a replica (pg_basebackup from new primary)"
echo "   - Or sync using pg_rewind if timeline compatible"
