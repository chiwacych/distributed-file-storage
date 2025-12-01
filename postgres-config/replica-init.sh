#!/bin/bash
set -e

# Wait for primary to be ready
echo "Waiting for primary database to be ready..."
until pg_isready -h postgres-primary -p 5432 -U dfsuser; do
  echo "Primary database is unavailable - sleeping"
  sleep 2
done

echo "Primary database is ready"

# Remove any existing data
rm -rf ${PGDATA}/*

# Create base backup from primary
echo "Creating base backup from primary..."
PGPASSWORD=replicator123 pg_basebackup -h postgres-primary -D ${PGDATA} -U replicator -v -P -W -R

# Configure standby
echo "Configuring standby database..."
cat >> ${PGDATA}/postgresql.conf <<EOF

# Replica settings
hot_standby = on
EOF

echo "Replica configured successfully"
