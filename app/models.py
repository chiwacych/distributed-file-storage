from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class FileMetadata(Base):
    """Store metadata about uploaded files"""
    __tablename__ = "file_metadata"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)  # in bytes
    content_type = Column(String(100))
    user_id = Column(String(100), index=True)
    bucket_name = Column(String(100), nullable=False)
    object_key = Column(String(500), nullable=False, unique=True)
    checksum = Column(String(64))  # MD5 or SHA256
    upload_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    last_accessed = Column(DateTime(timezone=True))
    is_deleted = Column(Boolean, default=False)
    description = Column(Text)
    
    def __repr__(self):
        return f"<FileMetadata(id={self.id}, filename='{self.filename}', size={self.file_size})>"


class UploadLog(Base):
    """Track all upload operations"""
    __tablename__ = "upload_logs"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, index=True)
    filename = Column(String(255), nullable=False)
    user_id = Column(String(100))
    status = Column(String(50), nullable=False)  # success, failed, partial
    minio_node = Column(String(50))  # which node received the upload
    error_message = Column(Text)
    upload_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    upload_duration = Column(Float)  # in seconds
    
    def __repr__(self):
        return f"<UploadLog(id={self.id}, filename='{self.filename}', status='{self.status}')>"


class ReplicationStatus(Base):
    """Track replication status across MinIO nodes"""
    __tablename__ = "replication_status"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, index=True)
    object_key = Column(String(500), nullable=False)
    node_name = Column(String(50), nullable=False)  # minio1, minio2, minio3
    is_replicated = Column(Boolean, default=False)
    replication_timestamp = Column(DateTime(timezone=True))
    verification_timestamp = Column(DateTime(timezone=True))
    is_verified = Column(Boolean, default=False)
    checksum = Column(String(64))
    error_message = Column(Text)
    
    def __repr__(self):
        return f"<ReplicationStatus(file_id={self.file_id}, node='{self.node_name}', replicated={self.is_replicated})>"


class NodeHealth(Base):
    """Monitor MinIO node health status"""
    __tablename__ = "node_health"

    id = Column(Integer, primary_key=True, index=True)
    node_name = Column(String(50), nullable=False, unique=True)
    endpoint = Column(String(100), nullable=False)
    is_healthy = Column(Boolean, default=True)
    last_check = Column(DateTime(timezone=True), server_default=func.now())
    total_files = Column(Integer, default=0)
    total_size = Column(Integer, default=0)  # in bytes
    status_message = Column(String(255))
    
    def __repr__(self):
        return f"<NodeHealth(node='{self.node_name}', healthy={self.is_healthy})>"
