#!/usr/bin/env python3
"""
PostgreSQL Replication Monitor
Checks replication status and lag for all replicas
"""
import os
import psycopg2
from datetime import datetime

def check_primary_status():
    """Check primary database replication status"""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    
    print("=" * 60)
    print("PRIMARY DATABASE STATUS")
    print("=" * 60)
    
    # Check replication slots
    cur.execute("""
        SELECT slot_name, slot_type, active, restart_lsn 
        FROM pg_replication_slots;
    """)
    
    slots = cur.fetchall()
    if slots:
        print("\nReplication Slots:")
        for slot in slots:
            print(f"  - {slot[0]}: {slot[1]} (Active: {slot[2]})")
    else:
        print("\nNo replication slots configured")
    
    # Check WAL senders (streaming replication connections)
    cur.execute("""
        SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn,
               sync_state, application_name
        FROM pg_stat_replication;
    """)
    
    replicas = cur.fetchall()
    if replicas:
        print(f"\nActive Replicas: {len(replicas)}")
        for i, replica in enumerate(replicas, 1):
            print(f"\n  Replica {i}:")
            print(f"    Client: {replica[0]}")
            print(f"    State: {replica[1]}")
            print(f"    Sync State: {replica[5]}")
            print(f"    Application: {replica[6] if replica[6] else 'N/A'}")
    else:
        print("\nNo active replica connections")
    
    cur.close()
    conn.close()


def check_replica_status(replica_url, replica_name):
    """Check replica database status"""
    try:
        conn = psycopg2.connect(replica_url)
        cur = conn.cursor()
        
        print(f"\n{replica_name.upper()} STATUS")
        print("-" * 60)
        
        # Check if in recovery mode (replica)
        cur.execute("SELECT pg_is_in_recovery();")
        in_recovery = cur.fetchone()[0]
        print(f"In Recovery Mode: {in_recovery}")
        
        if in_recovery:
            # Check replication lag
            cur.execute("""
                SELECT NOW() - pg_last_xact_replay_timestamp() AS replication_lag;
            """)
            lag = cur.fetchone()[0]
            if lag:
                print(f"Replication Lag: {lag}")
            else:
                print("Replication Lag: No transactions yet")
            
            # Check last received LSN
            cur.execute("SELECT pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn();")
            lsns = cur.fetchone()
            print(f"Last Received LSN: {lsns[0]}")
            print(f"Last Replayed LSN: {lsns[1]}")
        else:
            print("WARNING: This database is NOT in recovery mode (not a replica!)")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error connecting to {replica_name}: {e}")


def main():
    print(f"\n{'=' * 60}")
    print(f"PostgreSQL Replication Status Check")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")
    
    # Check primary
    try:
        check_primary_status()
    except Exception as e:
        print(f"Error checking primary: {e}")
    
    # Check replicas
    replica1_url = os.getenv("DATABASE_REPLICA1_URL")
    replica2_url = os.getenv("DATABASE_REPLICA2_URL")
    
    if replica1_url:
        check_replica_status(replica1_url, "Replica 1")
    
    if replica2_url:
        check_replica_status(replica2_url, "Replica 2")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
