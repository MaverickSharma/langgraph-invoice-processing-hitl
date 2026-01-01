"""
Database setup and connection management
"""
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Boolean, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DB_CONN", "sqlite:///./demo.db")

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# Database Models
class CheckpointDB(Base):
    """Checkpoint table for storing workflow state"""
    __tablename__ = "checkpoints"
    
    checkpoint_id = Column(String, primary_key=True, index=True)
    workflow_id = Column(String, index=True)
    workflow_name = Column(String)
    state_blob = Column(JSON)  # Serialized WorkflowState
    stage_id = Column(String)
    status = Column(String, default="CREATED")
    reason_for_hold = Column(Text)
    priority = Column(Integer, default=5)
    
    # Invoice context
    invoice_id = Column(String, index=True)
    vendor_name = Column(String)
    amount = Column(Float)
    currency = Column(String, default="USD")
    match_score = Column(Float, nullable=True)
    discrepancy_details = Column(JSON, nullable=True)
    
    # Review information
    review_url = Column(String)
    reviewed_at = Column(DateTime, nullable=True)
    reviewer_id = Column(String, nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    decision = Column(String, nullable=True)
    
    # Resume information
    resume_token = Column(String, nullable=True)
    resumed_at = Column(DateTime, nullable=True)
    next_stage = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


class HumanReviewQueueDB(Base):
    """Human review queue table"""
    __tablename__ = "human_review_queue"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    checkpoint_id = Column(String, index=True)
    workflow_id = Column(String, index=True)
    invoice_id = Column(String, index=True)
    vendor_name = Column(String)
    amount = Column(Float)
    currency = Column(String, default="USD")
    reason_for_hold = Column(Text)
    review_url = Column(String)
    priority = Column(Integer, default=5)
    status = Column(String, default="AWAITING_REVIEW")
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkflowExecutionDB(Base):
    """Workflow execution tracking table"""
    __tablename__ = "workflow_executions"
    
    workflow_id = Column(String, primary_key=True, index=True)
    workflow_name = Column(String)
    status = Column(String, default="INITIATED")
    current_stage = Column(String)
    
    # Invoice information
    invoice_id = Column(String, index=True)
    vendor_name = Column(String)
    amount = Column(Float)
    currency = Column(String, default="USD")
    
    # Execution state
    state_data = Column(JSON)  # Current WorkflowState
    stage_outputs = Column(JSON)  # List of stage outputs
    errors = Column(JSON, default=[])
    
    # Tool tracking
    bigtool_selections = Column(JSON, default={})
    mcp_server_calls = Column(JSON, default=[])
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class AuditLogDB(Base):
    """Audit log for all workflow actions"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String, index=True)
    stage_id = Column(String)
    action = Column(String)
    actor = Column(String)  # system, user, mcp_client, etc.
    details = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)


# Database utility functions
def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized successfully")


def drop_db():
    """Drop all database tables (use with caution!)"""
    Base.metadata.drop_all(bind=engine)
    print("⚠️  Database tables dropped")


def reset_db():
    """Reset database (drop and recreate)"""
    drop_db()
    init_db()
    print("🔄 Database reset complete")


if __name__ == "__main__":
    # Initialize database when run directly
    init_db()
