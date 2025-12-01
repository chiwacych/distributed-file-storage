#!/bin/bash
set -e

# Configure PostgreSQL for replication
echo "Configuring primary database for replication..."

# Update postgresql.conf for replication
cat >> ${PGDATA}/postgresql.conf <<EOF

# Replication settings
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
hot_standby = on
archive_mode = on
archive_command = '/bin/true'
EOF

# Configure pg_hba.conf to allow replication connections
cat >> ${PGDATA}/pg_hba.conf <<EOF

# Replication connections
host    replication     replicator      0.0.0.0/0               md5
EOF

# Create replication user
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'replicator123';
    CREATE PUBLICATION minio_dfs_pub FOR ALL TABLES;
EOSQL

echo "Primary database configured for replication"
