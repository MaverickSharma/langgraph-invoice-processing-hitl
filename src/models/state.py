"""
Data models for workflow state management
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    INITIATED = "INITIATED"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    MANUAL_HANDOFF = "MANUAL_HANDOFF"


class StageStatus(str, Enum):
    """Individual stage execution status"""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class LineItem(BaseModel):
    """Invoice line item"""
    desc: str
    qty: float
    unit_price: float
    total: float


class InvoicePayload(BaseModel):
    """Raw invoice input payload"""
    invoice_id: str
    vendor_name: str
    vendor_tax_id: Optional[str] = None
    invoice_date: str
    due_date: str
    amount: float
    currency: str = "USD"
    line_items: List[LineItem] = []
    attachments: List[str] = []
    po_reference: Optional[str] = None


class VendorProfile(BaseModel):
    """Enriched vendor information"""
    normalized_name: str
    tax_id: Optional[str] = None
    risk_score: float = 0.0
    credit_score: Optional[float] = None
    enrichment_meta: Dict[str, Any] = {}


class MatchEvidence(BaseModel):
    """Evidence from matching process"""
    po_number: Optional[str] = None
    po_amount: Optional[float] = None
    invoice_amount: float
    discrepancy: float = 0.0
    discrepancy_items: List[str] = []


class StageOutput(BaseModel):
    """Generic stage output container"""
    stage_id: str
    status: StageStatus
    data: Dict[str, Any] = {}
    errors: List[str] = []
    tool_selections: Dict[str, str] = {}
    mcp_calls: List[str] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WorkflowState(BaseModel):
    """
    Complete workflow state that persists across all stages.
    This is the state graph for LangGraph.
    """
    # Workflow metadata
    workflow_id: str
    workflow_name: str = "InvoiceProcessing_v1"
    status: WorkflowStatus = WorkflowStatus.INITIATED
    current_stage: str = "INTAKE"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Input data
    invoice_payload: Optional[InvoicePayload] = None
    
    # Stage 1: INTAKE outputs
    raw_id: Optional[str] = None
    ingest_ts: Optional[str] = None
    validated: bool = False
    
    # Stage 2: UNDERSTAND outputs
    parsed_invoice: Optional[Dict[str, Any]] = None
    invoice_text: Optional[str] = None
    parsed_line_items: List[Dict[str, Any]] = []
    detected_pos: List[str] = []
    
    # Stage 3: PREPARE outputs
    vendor_profile: Optional[VendorProfile] = None
    normalized_invoice: Optional[Dict[str, Any]] = None
    flags: Dict[str, Any] = {}
    
    # Stage 4: RETRIEVE outputs
    matched_pos: List[Dict[str, Any]] = []
    matched_grns: List[Dict[str, Any]] = []
    history: List[Dict[str, Any]] = []
    
    # Stage 5: MATCH_TWO_WAY outputs
    match_score: float = 0.0
    match_result: str = "PENDING"
    tolerance_pct: float = 0.0
    match_evidence: Optional[MatchEvidence] = None
    
    # Stage 6: CHECKPOINT_HITL outputs
    hitl_checkpoint_id: Optional[str] = None
    review_url: Optional[str] = None
    paused_reason: Optional[str] = None
    requires_human_review: bool = False
    
    # Stage 7: HITL_DECISION outputs
    human_decision: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewer_notes: Optional[str] = None
    resume_token: Optional[str] = None
    next_stage: Optional[str] = None
    
    # Stage 8: RECONCILE outputs
    accounting_entries: List[Dict[str, Any]] = []
    reconciliation_report: Optional[Dict[str, Any]] = None
    
    # Stage 9: APPROVE outputs
    approval_status: str = "PENDING"
    approver_id: Optional[str] = None
    approval_amount_threshold: float = 10000.0
    
    # Stage 10: POSTING outputs
    posted: bool = False
    erp_txn_id: Optional[str] = None
    scheduled_payment_id: Optional[str] = None
    
    # Stage 11: NOTIFY outputs
    notify_status: Dict[str, Any] = {}
    notified_parties: List[str] = []
    
    # Stage 12: COMPLETE outputs
    final_payload: Optional[Dict[str, Any]] = None
    audit_log: List[Dict[str, Any]] = []
    
    # Execution tracking
    stage_outputs: List[StageOutput] = []
    errors: List[str] = []
    
    # Tool and MCP tracking
    bigtool_selections: Dict[str, str] = {}
    mcp_server_calls: List[Dict[str, Any]] = []
    
    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class StateUpdate(BaseModel):
    """Incremental state update from a stage"""
    stage_id: str
    updates: Dict[str, Any]
    append_to: Optional[Dict[str, List[Any]]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
