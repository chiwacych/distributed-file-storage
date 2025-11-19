from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
import hashlib
from datetime import datetime
import io
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from database import get_db, init_db, engine
from models import FileMetadata, UploadLog, ReplicationStatus, NodeHealth
from minio_client import minio_cluster
from redis_client import redis_cache
from replication_manager import replication_manager

# Thread pool for running blocking operations (reduced, replication has its own)
thread_pool = ThreadPoolExecutor(max_workers=4)

# Initialize FastAPI app
app = FastAPI(
    title="Distributed File Storage System",
    description="A fault-tolerant distributed file storage system using MinIO, PostgreSQL, and Redis",
    version="1.0.0"
)

# Mount static files directory
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Background task flag
background_tasks_running = False


async def auto_sync_replication():
    """Background task to automatically sync incomplete replications using robust manager"""
    global background_tasks_running
    
    while background_tasks_running:
        try:
            print("🔄 Auto-sync: Checking for incomplete replications...")
            
            # Use the replication manager with a database session
            from database import SessionLocal
            db = SessionLocal()
            
            try:
                # Sync only recent files (last 24 hours) to avoid processing too many
                result = await replication_manager.sync_all(
                    db,
                    priority_recent=True,
                    max_age_hours=24
                )
                
                if result["status"] == "success":
                    summary = result["summary"]
                    if summary["synced"] > 0:
                        print(f"✓ Auto-sync completed: {summary['synced']} file(s) synced")
                    else:
                        print(f"✓ Auto-sync: {summary['complete']} files fully replicated, {summary['pending']} pending")
                elif result["status"] == "busy":
                    print("⏳ Auto-sync: Skipped (manual sync in progress)")
                    
            finally:
                db.close()
                
        except Exception as e:
            print(f"✗ Auto-sync error: {str(e)}")
        
        # Wait 30 seconds before next check
        await asyncio.sleep(30)


@app.on_event("startup")
async def startup_event():
    """Initialize database and MinIO buckets on startup"""
    global background_tasks_running
    
    print("🚀 Starting Distributed File Storage System...")
    
    # Initialize database
    init_db()
    print("✓ Database initialized")
    
    # Ensure buckets exist on all MinIO nodes
    bucket_results = minio_cluster.ensure_bucket("dfs-files")
    for node_id, result in bucket_results.items():
        print(f"  {node_id}: {result}")
    
    print("✓ MinIO cluster ready")
    
    # Start background replication sync task
    background_tasks_running = True
    asyncio.create_task(auto_sync_replication())
    print("✓ Auto-sync replication task started")
    
    print("✓ System startup complete!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global background_tasks_running
    background_tasks_running = False
    print("🛑 Shutting down background tasks...")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Redirect to admin dashboard by default"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Serve the admin dashboard"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/user", response_class=HTMLResponse)
async def user_portal(request: Request):
    """Serve the user portal"""
    return templates.TemplateResponse("user.html", {"request": request})


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(default="anonymous"),
    description: str = Form(default=""),
    db: Session = Depends(get_db)
):
    """
    Upload a file to the distributed file system
    - Uploads to all MinIO nodes for redundancy
    - Stores metadata in PostgreSQL
    - Invalidates cache
    """
    try:
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Calculate checksum
        checksum = hashlib.sha256(file_content).hexdigest()
        
        # Generate unique object key
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        object_key = f"{user_id}/{timestamp}_{file.filename}"
        
        # Upload to all MinIO nodes
        upload_start = datetime.now()
        upload_results = minio_cluster.upload_file_to_all_nodes(
            file_data=file_content,
            object_name=object_key,
            bucket_name="dfs-files",
            content_type=file.content_type or "application/octet-stream"
        )
        upload_duration = (datetime.now() - upload_start).total_seconds()
        
        # Count successful uploads
        successful_uploads = sum(1 for r in upload_results.values() if r["status"] == "success")
        
        # Create file metadata record
        file_metadata = FileMetadata(
            filename=file.filename,
            original_filename=file.filename,
            file_size=file_size,
            content_type=file.content_type,
            user_id=user_id,
            bucket_name="dfs-files",
            object_key=object_key,
            checksum=checksum,
            description=description
        )
        db.add(file_metadata)
        db.commit()
        db.refresh(file_metadata)
        
        # Log upload operation
        upload_log = UploadLog(
            file_id=file_metadata.id,
            filename=file.filename,
            user_id=user_id,
            status="success" if successful_uploads == 3 else "partial",
            minio_node="all_nodes",
            upload_duration=upload_duration
        )
        db.add(upload_log)
        
        # Create replication status records
        for node_id, result in upload_results.items():
            replication = ReplicationStatus(
                file_id=file_metadata.id,
                object_key=object_key,
                node_name=node_id,
                is_replicated=(result["status"] == "success"),
                replication_timestamp=datetime.now() if result["status"] == "success" else None,
                is_verified=False,
                checksum=checksum if result["status"] == "success" else None,
                error_message=result["message"] if result["status"] == "error" else None
            )
            db.add(replication)
        
        db.commit()
        
        # Invalidate file list cache
        redis_cache.invalidate_file_list()
        
        return {
            "status": "success",
            "message": f"File uploaded successfully to {successful_uploads}/3 nodes",
            "file_id": file_metadata.id,
            "filename": file.filename,
            "size": file_size,
            "checksum": checksum,
            "upload_duration": upload_duration,
            "replication_results": upload_results
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/api/files")
async def list_files(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all files in the system
    - Uses Redis cache if available
    - Falls back to database query
    """
    try:
        # Try to get from cache first
        cache_key = f"files:list:{user_id or 'all'}"
        cached_files = redis_cache.get(cache_key)
        
        if cached_files:
            return {
                "status": "success",
                "source": "cache",
                "files": cached_files
            }
        
        # Query database
        query = db.query(FileMetadata).filter(FileMetadata.is_deleted == False)
        if user_id:
            query = query.filter(FileMetadata.user_id == user_id)
        
        files = query.order_by(FileMetadata.upload_timestamp.desc()).all()
        
        files_data = []
        for f in files:
            files_data.append({
                "id": f.id,
                "filename": f.filename,
                "size": f.file_size,
                "content_type": f.content_type,
                "user_id": f.user_id,
                "upload_timestamp": f.upload_timestamp.isoformat(),
                "checksum": f.checksum,
                "description": f.description
            })
        
        # Cache the result
        redis_cache.set(cache_key, files_data, ttl=300)
        
        return {
            "status": "success",
            "source": "database",
            "files": files_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@app.get("/api/files/{file_id}")
async def get_file_info(
    file_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific file
    - Includes replication status across nodes
    - Uses Redis cache
    """
    try:
        # Try cache first
        cached_metadata = redis_cache.get_file_metadata(file_id)
        if cached_metadata:
            return {
                "status": "success",
                "source": "cache",
                "file": cached_metadata
            }
        
        # Query database
        file_meta = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
        if not file_meta:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Get replication status
        replication_status = db.query(ReplicationStatus).filter(
            ReplicationStatus.file_id == file_id
        ).all()
        
        replication_data = []
        for rep in replication_status:
            replication_data.append({
                "node": rep.node_name,
                "replicated": rep.is_replicated,
                "verified": rep.is_verified,
                "timestamp": rep.replication_timestamp.isoformat() if rep.replication_timestamp else None
            })
        
        file_data = {
            "id": file_meta.id,
            "filename": file_meta.filename,
            "size": file_meta.file_size,
            "content_type": file_meta.content_type,
            "user_id": file_meta.user_id,
            "upload_timestamp": file_meta.upload_timestamp.isoformat(),
            "checksum": file_meta.checksum,
            "description": file_meta.description,
            "replication_status": replication_data
        }
        
        # Cache the result
        redis_cache.set_file_metadata(file_id, file_data)
        
        return {
            "status": "success",
            "source": "database",
            "file": file_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get file info: {str(e)}")


@app.get("/api/files/{file_id}/download")
async def download_file(
    file_id: int,
    node: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Download a file from the distributed system
    - Attempts to fetch from specified node or any available node
    - Updates last accessed timestamp
    - Increments download counter in Redis
    """
    try:
        # Get file metadata
        file_meta = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
        if not file_meta:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Try to download from MinIO
        file_data = minio_cluster.get_file_from_node(
            object_name=file_meta.object_key,
            node_id=node,
            bucket_name="dfs-files"
        )
        
        if file_data is None:
            raise HTTPException(status_code=404, detail="File not found on any MinIO node")
        
        # Update last accessed timestamp
        file_meta.last_accessed = datetime.now()
        db.commit()
        
        # Increment download counter in Redis
        redis_cache.increment_downloads(file_id)
        
        # Return file as streaming response
        return StreamingResponse(
            io.BytesIO(file_data),
            media_type=file_meta.content_type or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{file_meta.filename}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@app.delete("/api/files/{file_id}")
async def delete_file(
    file_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a file from the distributed system
    - Removes from all MinIO nodes
    - Marks as deleted in database (soft delete)
    - Clears cache
    """
    try:
        # Get file metadata
        file_meta = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
        if not file_meta:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Delete from all MinIO nodes
        delete_results = minio_cluster.delete_file_from_all_nodes(
            object_name=file_meta.object_key,
            bucket_name="dfs-files"
        )
        
        # Mark as deleted in database (soft delete)
        file_meta.is_deleted = True
        db.commit()
        
        # Clear cache
        redis_cache.delete(f"file:metadata:{file_id}")
        redis_cache.invalidate_file_list()
        
        return {
            "status": "success",
            "message": "File deleted successfully",
            "delete_results": delete_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@app.get("/api/nodes/health")
async def get_nodes_health(db: Session = Depends(get_db)):
    """
    Get health status of all MinIO nodes
    - Checks connectivity to each node
    - Updates node health table
    - Uses Redis cache
    """
    try:
        # Get health status from MinIO cluster
        health_status = minio_cluster.get_node_health()
        
        # Update database and cache
        for node_id, health in health_status.items():
            # Update or create node health record
            node_health = db.query(NodeHealth).filter(NodeHealth.node_name == node_id).first()
            if node_health:
                node_health.is_healthy = health["healthy"]
                node_health.last_check = datetime.now()
                node_health.status_message = health["message"]
            else:
                node_health = NodeHealth(
                    node_name=node_id,
                    endpoint=health["endpoint"],
                    is_healthy=health["healthy"],
                    status_message=health["message"]
                )
                db.add(node_health)
            
            # Cache node health
            redis_cache.set_node_health(node_id, health, ttl=60)
        
        db.commit()
        
        return {
            "status": "success",
            "nodes": health_status
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@app.get("/api/stats")
async def get_system_stats(db: Session = Depends(get_db)):
    """Get system statistics"""
    try:
        total_files = db.query(FileMetadata).filter(FileMetadata.is_deleted == False).count()
        total_size = db.query(FileMetadata).filter(FileMetadata.is_deleted == False).with_entities(
            func.sum(FileMetadata.file_size)
        ).scalar() or 0
        
        total_uploads = db.query(UploadLog).count()
        successful_uploads = db.query(UploadLog).filter(UploadLog.status == "success").count()
        
        cache_stats = redis_cache.get_cache_stats()
        popular_files = redis_cache.get_popular_files(limit=5)
        
        return {
            "status": "success",
            "stats": {
                "total_files": total_files,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "total_uploads": total_uploads,
                "successful_uploads": successful_uploads,
                "success_rate": round(successful_uploads / max(total_uploads, 1) * 100, 2),
                "cache_stats": cache_stats,
                "popular_files": popular_files
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@app.get("/api/replication/verify/{file_id}")
async def verify_replication(
    file_id: int,
    db: Session = Depends(get_db)
):
    """Verify that a file is properly replicated across all nodes"""
    try:
        file_meta = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
        if not file_meta:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check file existence on all nodes
        existence_status = minio_cluster.check_file_exists_on_nodes(
            object_name=file_meta.object_key,
            bucket_name="dfs-files"
        )
        
        # Update replication status
        for node_id, exists in existence_status.items():
            replication = db.query(ReplicationStatus).filter(
                ReplicationStatus.file_id == file_id,
                ReplicationStatus.node_name == node_id
            ).first()
            
            if replication:
                replication.is_verified = exists
                replication.verification_timestamp = datetime.now()
        
        db.commit()
        
        return {
            "status": "success",
            "file_id": file_id,
            "replication_status": existence_status,
            "fully_replicated": all(existence_status.values())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@app.post("/api/replication/sync/{file_id}")
async def sync_replication(
    file_id: int,
    db: Session = Depends(get_db)
):
    """Sync/repair replication for a file by copying it to missing nodes"""
    try:
        file_meta = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
        if not file_meta:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check which nodes have the file
        existence_status = minio_cluster.check_file_exists_on_nodes(
            object_name=file_meta.object_key,
            bucket_name="dfs-files"
        )
        
        # Find a source node that has the file
        source_node = None
        for node_id, exists in existence_status.items():
            if exists:
                source_node = node_id
                break
        
        if not source_node:
            raise HTTPException(status_code=404, detail="File not found on any node")
        
        # Get the file from the source node
        file_data = minio_cluster.get_file_from_node(
            object_name=file_meta.object_key,
            node_id=source_node,
            bucket_name="dfs-files"
        )
        
        if not file_data:
            raise HTTPException(status_code=500, detail="Failed to retrieve file from source node")
        
        # Upload to missing nodes
        sync_results = {}
        for node_id, exists in existence_status.items():
            if not exists:
                try:
                    node_info = minio_cluster.nodes[node_id]
                    client = node_info["client"]
                    file_stream = io.BytesIO(file_data)
                    
                    start_time = datetime.now()
                    client.put_object(
                        "dfs-files",
                        file_meta.object_key,
                        file_stream,
                        len(file_data),
                        content_type=file_meta.content_type or "application/octet-stream"
                    )
                    upload_time = (datetime.now() - start_time).total_seconds()
                    
                    sync_results[node_id] = {
                        "status": "success",
                        "message": f"Synced to {node_info['name']}",
                        "upload_time": upload_time
                    }
                    
                    # Update replication status
                    replication = db.query(ReplicationStatus).filter(
                        ReplicationStatus.file_id == file_id,
                        ReplicationStatus.node_name == node_id
                    ).first()
                    
                    if replication:
                        replication.is_replicated = True
                        replication.replication_timestamp = datetime.now()
                        replication.is_verified = True
                        replication.verification_timestamp = datetime.now()
                        replication.checksum = file_meta.checksum
                        replication.error_message = None
                    else:
                        # Create new replication record
                        new_replication = ReplicationStatus(
                            file_id=file_id,
                            object_key=file_meta.object_key,
                            node_name=node_id,
                            is_replicated=True,
                            replication_timestamp=datetime.now(),
                            is_verified=True,
                            verification_timestamp=datetime.now(),
                            checksum=file_meta.checksum
                        )
                        db.add(new_replication)
                    
                except Exception as e:
                    sync_results[node_id] = {
                        "status": "error",
                        "message": str(e)
                    }
            else:
                sync_results[node_id] = {
                    "status": "skipped",
                    "message": "File already exists on this node"
                }
        
        db.commit()
        
        # Verify final state
        final_status = minio_cluster.check_file_exists_on_nodes(
            object_name=file_meta.object_key,
            bucket_name="dfs-files"
        )
        
        return {
            "status": "success",
            "file_id": file_id,
            "source_node": source_node,
            "sync_results": sync_results,
            "final_replication_status": final_status,
            "fully_replicated": all(final_status.values())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@app.post("/api/replication/sync-all")
async def sync_all_files(db: Session = Depends(get_db)):
    """Sync replication for all files using robust replication manager"""
    try:
        result = await replication_manager.sync_all(db, priority_recent=True)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
