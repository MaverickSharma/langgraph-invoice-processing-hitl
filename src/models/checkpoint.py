"""
Checkpoint data models for HITL workflow persistence
"""
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class CheckpointStatus(str, Enum):
    """Checkpoint status"""
    CREATED = "CREATED"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    REVIEWED = "REVIEWED"
    RESUMED = "RESUMED"
    EXPIRED = "EXPIRED"


class HumanDecision(str, Enum):
    """Human review decision"""
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"
    REQUEST_INFO = "REQUEST_INFO"


class Checkpoint(BaseModel):
    """
    Checkpoint model for storing workflow state at HITL points
    """
    checkpoint_id: str
    workflow_id: str
    workflow_name: str
    
    # State snapshot
    state_blob: Dict[str, Any]  # Serialized WorkflowState
    stage_id: str  # Stage where checkpoint was created
    
    # Review information
    status: CheckpointStatus = CheckpointStatus.CREATED
    reason_for_hold: str
    priority: int = 5  # 1=highest, 10=lowest
    
    # Invoice context for reviewer
    invoice_id: str
    vendor_name: str
    amount: float
    currency: str = "USD"
    match_score: Optional[float] = None
    discrepancy_details: Optional[Dict[str, Any]] = None
    
    # Human review
    review_url: str
    reviewed_at: Optional[datetime] = None
    reviewer_id: Optional[str] = None
    reviewer_notes: Optional[str] = None
    decision: Optional[HumanDecision] = None
    
    # Resume information
    resume_token: Optional[str] = None
    resumed_at: Optional[datetime] = None
    next_stage: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class HumanReviewQueueItem(BaseModel):
    """
    Item in the human review queue
    """
    checkpoint_id: str
    workflow_id: str
    invoice_id: str
    vendor_name: str
    amount: float
    currency: str = "USD"
    created_at: datetime
    reason_for_hold: str
    review_url: str
    priority: int = 5
    status: CheckpointStatus = CheckpointStatus.AWAITING_REVIEW
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ReviewDecisionRequest(BaseModel):
    """Request model for human review decision"""
    checkpoint_id: str
    decision: HumanDecision
    notes: Optional[str] = None
    reviewer_id: str
    
    class Config:
        use_enum_values = True


class ReviewDecisionResponse(BaseModel):
    """Response model for human review decision"""
    checkpoint_id: str
    resume_token: str
    next_stage: str
    message: str
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
