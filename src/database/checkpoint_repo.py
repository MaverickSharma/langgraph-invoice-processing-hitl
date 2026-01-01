"""
Checkpoint repository for database operations
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
import json

from ..database.db import CheckpointDB, HumanReviewQueueDB
from ..models.checkpoint import (
    Checkpoint, 
    CheckpointStatus, 
    HumanDecision,
    HumanReviewQueueItem
)
from ..models.state import WorkflowState


class CheckpointRepository:
    """Repository for checkpoint database operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_checkpoint(
        self, 
        workflow_state: WorkflowState,
        reason_for_hold: str,
        priority: int = 5
    ) -> Checkpoint:
        """
        Create a new checkpoint from workflow state
        """
        checkpoint_id = f"chk_{uuid.uuid4().hex[:12]}"
        review_url = f"/human-review/review/{checkpoint_id}"
        
        # Serialize state to JSON-compatible dict (converts datetime to ISO strings)
        state_blob = json.loads(workflow_state.json())
        
        # Create checkpoint model
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_state.workflow_id,
            workflow_name=workflow_state.workflow_name,
            state_blob=state_blob,
            stage_id=workflow_state.current_stage,
            reason_for_hold=reason_for_hold,
            priority=priority,
            invoice_id=workflow_state.invoice_payload.invoice_id if workflow_state.invoice_payload else "unknown",
            vendor_name=workflow_state.invoice_payload.vendor_name if workflow_state.invoice_payload else "unknown",
            amount=workflow_state.invoice_payload.amount if workflow_state.invoice_payload else 0,
            currency=workflow_state.invoice_payload.currency if workflow_state.invoice_payload else "USD",
            match_score=workflow_state.match_score,
            discrepancy_details=json.loads(workflow_state.match_evidence.json()) if workflow_state.match_evidence else None,
            review_url=review_url,
            status=CheckpointStatus.AWAITING_REVIEW,
            expires_at=datetime.utcnow() + timedelta(days=7)  # 7 days to review
        )
        
        # Save to database
        db_checkpoint = CheckpointDB(
            checkpoint_id=checkpoint.checkpoint_id,
            workflow_id=checkpoint.workflow_id,
            workflow_name=checkpoint.workflow_name,
            state_blob=json.dumps(checkpoint.state_blob),  # Serialize to JSON string
            stage_id=checkpoint.stage_id,
            status=checkpoint.status.value if hasattr(checkpoint.status, 'value') else checkpoint.status,
            reason_for_hold=checkpoint.reason_for_hold,
            priority=checkpoint.priority,
            invoice_id=checkpoint.invoice_id,
            vendor_name=checkpoint.vendor_name,
            amount=checkpoint.amount,
            currency=checkpoint.currency,
            match_score=checkpoint.match_score,
            discrepancy_details=json.dumps(checkpoint.discrepancy_details) if checkpoint.discrepancy_details else None,
            review_url=checkpoint.review_url,
            reviewed_at=checkpoint.reviewed_at,
            reviewer_id=checkpoint.reviewer_id,
            reviewer_notes=checkpoint.reviewer_notes,
            decision=checkpoint.decision.value if checkpoint.decision and hasattr(checkpoint.decision, 'value') else checkpoint.decision,
            resume_token=checkpoint.resume_token,
            resumed_at=checkpoint.resumed_at,
            next_stage=checkpoint.next_stage,
            created_at=checkpoint.created_at,
            updated_at=checkpoint.updated_at,
            expires_at=checkpoint.expires_at
        )
        self.db.add(db_checkpoint)
        self.db.commit()
        self.db.refresh(db_checkpoint)
        
        # Add to human review queue
        queue_item = HumanReviewQueueDB(
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_state.workflow_id,
            invoice_id=checkpoint.invoice_id,
            vendor_name=checkpoint.vendor_name,
            amount=checkpoint.amount,
            currency=checkpoint.currency,
            reason_for_hold=reason_for_hold,
            review_url=review_url,
            priority=priority,
            status=CheckpointStatus.AWAITING_REVIEW.value
        )
        self.db.add(queue_item)
        self.db.commit()
        
        return checkpoint
    
    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Get checkpoint by ID"""
        db_checkpoint = self.db.query(CheckpointDB).filter(
            CheckpointDB.checkpoint_id == checkpoint_id
        ).first()
        
        if not db_checkpoint:
            return None
        
        # Deserialize JSON fields from string
        state_blob = json.loads(db_checkpoint.state_blob) if isinstance(db_checkpoint.state_blob, str) else db_checkpoint.state_blob
        discrepancy_details = json.loads(db_checkpoint.discrepancy_details) if db_checkpoint.discrepancy_details and isinstance(db_checkpoint.discrepancy_details, str) else db_checkpoint.discrepancy_details
        
        return Checkpoint(
            checkpoint_id=db_checkpoint.checkpoint_id,
            workflow_id=db_checkpoint.workflow_id,
            workflow_name=db_checkpoint.workflow_name,
            state_blob=state_blob,
            stage_id=db_checkpoint.stage_id,
            status=CheckpointStatus(db_checkpoint.status),
            reason_for_hold=db_checkpoint.reason_for_hold,
            priority=db_checkpoint.priority,
            invoice_id=db_checkpoint.invoice_id,
            vendor_name=db_checkpoint.vendor_name,
            amount=db_checkpoint.amount,
            currency=db_checkpoint.currency,
            match_score=db_checkpoint.match_score,
            discrepancy_details=discrepancy_details,
            review_url=db_checkpoint.review_url,
            reviewed_at=db_checkpoint.reviewed_at,
            reviewer_id=db_checkpoint.reviewer_id,
            reviewer_notes=db_checkpoint.reviewer_notes,
            decision=HumanDecision(db_checkpoint.decision) if db_checkpoint.decision else None,
            resume_token=db_checkpoint.resume_token,
            resumed_at=db_checkpoint.resumed_at,
            next_stage=db_checkpoint.next_stage,
            created_at=db_checkpoint.created_at,
            updated_at=db_checkpoint.updated_at,
            expires_at=db_checkpoint.expires_at
        )
    
    def update_checkpoint_with_decision(
        self,
        checkpoint_id: str,
        decision: HumanDecision,
        reviewer_id: str,
        notes: Optional[str] = None
    ) -> Optional[Checkpoint]:
        """Update checkpoint with human decision"""
        db_checkpoint = self.db.query(CheckpointDB).filter(
            CheckpointDB.checkpoint_id == checkpoint_id
        ).first()
        
        if not db_checkpoint:
            return None
        
        # Generate resume token
        resume_token = f"resume_{uuid.uuid4().hex[:16]}"
        
        # Determine next stage based on decision
        next_stage = "RECONCILE" if decision == HumanDecision.ACCEPT else "COMPLETE"
        
        # Update checkpoint
        db_checkpoint.status = CheckpointStatus.REVIEWED.value
        db_checkpoint.decision = decision.value
        db_checkpoint.reviewer_id = reviewer_id
        db_checkpoint.reviewer_notes = notes
        db_checkpoint.reviewed_at = datetime.utcnow()
        db_checkpoint.resume_token = resume_token
        db_checkpoint.next_stage = next_stage
        db_checkpoint.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(db_checkpoint)
        
        # Update review queue
        queue_item = self.db.query(HumanReviewQueueDB).filter(
            HumanReviewQueueDB.checkpoint_id == checkpoint_id
        ).first()
        if queue_item:
            queue_item.status = CheckpointStatus.REVIEWED.value
            self.db.commit()
        
        return self.get_checkpoint(checkpoint_id)
    
    def mark_checkpoint_resumed(self, checkpoint_id: str):
        """Mark checkpoint as resumed"""
        db_checkpoint = self.db.query(CheckpointDB).filter(
            CheckpointDB.checkpoint_id == checkpoint_id
        ).first()
        
        if db_checkpoint:
            db_checkpoint.status = CheckpointStatus.RESUMED.value
            db_checkpoint.resumed_at = datetime.utcnow()
            self.db.commit()
    
    def get_pending_reviews(self) -> List[HumanReviewQueueItem]:
        """Get all pending review items"""
        queue_items = self.db.query(HumanReviewQueueDB).filter(
            HumanReviewQueueDB.status == CheckpointStatus.AWAITING_REVIEW.value
        ).order_by(
            HumanReviewQueueDB.priority.asc(),
            HumanReviewQueueDB.created_at.asc()
        ).all()
        
        return [
            HumanReviewQueueItem(**{
                k: v for k, v in item.__dict__.items() if not k.startswith('_')
            })
            for item in queue_items
        ]
    
    def get_workflow_checkpoints(self, workflow_id: str) -> List[Checkpoint]:
        """Get all checkpoints for a workflow"""
        db_checkpoints = self.db.query(CheckpointDB).filter(
            CheckpointDB.workflow_id == workflow_id
        ).order_by(CheckpointDB.created_at.desc()).all()
        
        return [
            Checkpoint(**{
                **{k: v for k, v in cp.__dict__.items() if not k.startswith('_')},
                'status': CheckpointStatus(cp.status),
                'decision': HumanDecision(cp.decision) if cp.decision else None
            })
            for cp in db_checkpoints
        ]
