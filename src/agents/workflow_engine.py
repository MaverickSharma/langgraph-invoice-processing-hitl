"""
LangGraph Invoice Processing Workflow Engine
Complete implementation of all 12 stages with state management and HITL
"""
from typing import Dict, Any, Optional, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
import uuid
from datetime import datetime
import structlog
import os

from ..models.state import WorkflowState, WorkflowStatus, StageOutput, StageStatus
from ..models.checkpoint import CheckpointStatus, HumanDecision
from ..mcp.mcp_client import get_mcp_client, MCPAbility
from ..tools.bigtool import get_bigtool
from ..database.db import SessionLocal
from ..database.checkpoint_repo import CheckpointRepository

logger = structlog.get_logger()


class InvoiceProcessingWorkflow:
    """
    LangGraph-based invoice processing workflow with 12 stages,
    HITL checkpointing, and MCP integration
    """
    
    def __init__(self, checkpoint_path: str = "./checkpoints.db"):
        """Initialize workflow with checkpointer"""
        self.mcp_client = get_mcp_client()
        self.bigtool = get_bigtool()
        self.checkpoint_path = checkpoint_path
        
        # Create SQLite connection and checkpointer
        import sqlite3
        self.conn = sqlite3.connect(checkpoint_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self.conn)
        
        # Build the workflow graph
        self.graph = self._build_graph()
        self.app = self.graph.compile(checkpointer=self.checkpointer)
        
        logger.info("workflow_initialized", checkpoint_path=checkpoint_path)
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow with all stages"""
        # Create state graph
        workflow = StateGraph(WorkflowState)
        
        # Add all nodes (stages)
        workflow.add_node("INTAKE", self.stage_intake)
        workflow.add_node("UNDERSTAND", self.stage_understand)
        workflow.add_node("PREPARE", self.stage_prepare)
        workflow.add_node("RETRIEVE", self.stage_retrieve)
        workflow.add_node("MATCH_TWO_WAY", self.stage_match_two_way)
        workflow.add_node("CHECKPOINT_HITL", self.stage_checkpoint_hitl)
        workflow.add_node("HITL_DECISION", self.stage_hitl_decision)
        workflow.add_node("RECONCILE", self.stage_reconcile)
        workflow.add_node("APPROVE", self.stage_approve)
        workflow.add_node("POSTING", self.stage_posting)
        workflow.add_node("NOTIFY", self.stage_notify)
        workflow.add_node("COMPLETE", self.stage_complete)
        
        # Set entry point
        workflow.set_entry_point("INTAKE")
        
        # Define linear flow for deterministic stages
        workflow.add_edge("INTAKE", "UNDERSTAND")
        workflow.add_edge("UNDERSTAND", "PREPARE")
        workflow.add_edge("PREPARE", "RETRIEVE")
        workflow.add_edge("RETRIEVE", "MATCH_TWO_WAY")
        
        # Conditional routing after MATCH_TWO_WAY
        workflow.add_conditional_edges(
            "MATCH_TWO_WAY",
            self._route_after_match,
            {
                "RECONCILE": "RECONCILE",  # Match succeeded
                "CHECKPOINT_HITL": "CHECKPOINT_HITL"  # Match failed, needs review
            }
        )
        
        # After checkpoint, pause - execution resumes at HITL_DECISION
        workflow.add_edge("CHECKPOINT_HITL", "HITL_DECISION")
        
        # Conditional routing after human decision
        workflow.add_conditional_edges(
            "HITL_DECISION",
            self._route_after_hitl,
            {
                "RECONCILE": "RECONCILE",  # Human accepted
                "COMPLETE": "COMPLETE"  # Human rejected
            }
        )
        
        # Continue linear flow after reconciliation
        workflow.add_edge("RECONCILE", "APPROVE")
        workflow.add_edge("APPROVE", "POSTING")
        workflow.add_edge("POSTING", "NOTIFY")
        workflow.add_edge("NOTIFY", "COMPLETE")
        
        # End after complete
        workflow.add_edge("COMPLETE", END)
        
        return workflow
    
    def _route_after_match(self, state: WorkflowState) -> str:
        """Route based on match result"""
        if state.match_result == "MATCHED":
            return "RECONCILE"
        else:
            return "CHECKPOINT_HITL"
    
    def _route_after_hitl(self, state: WorkflowState) -> str:
        """Route based on human decision"""
        if state.human_decision == HumanDecision.ACCEPT:
            return "RECONCILE"
        else:
            # Reject or other decision -> Complete with manual handoff
            return "COMPLETE"
    
    # ========== Stage 1: INTAKE ==========
    def stage_intake(self, state: WorkflowState) -> Dict[str, Any]:
        """Accept and validate invoice payload"""
        logger.info("stage_started", stage="INTAKE", workflow_id=state.workflow_id)
        
        try:
            # Select storage tool
            storage_selection = self.bigtool.select(
                "db",
                {"environment": os.getenv("ENVIRONMENT", "development")}
            )
            
            # Validate schema using MCP COMMON server
            validation_result = self.mcp_client.execute_ability(
                MCPAbility.VALIDATE_SCHEMA,
                {"invoice_payload": state.invoice_payload.dict() if state.invoice_payload else {}},
                {"workflow_id": state.workflow_id, "stage": "INTAKE"}
            )
            
            validated = validation_result.get("data", {}).get("validated", False)
            
            # Generate raw_id
            raw_id = f"raw_{uuid.uuid4().hex[:12]}"
            ingest_ts = datetime.utcnow().isoformat()
            
            # Track bigtool selection and MCP calls
            state.bigtool_selections["INTAKE_storage"] = storage_selection.selected_tool
            state.mcp_server_calls.append({
                "stage": "INTAKE",
                "ability": "validate_schema",
                "server": "COMMON",
                "timestamp": ingest_ts
            })
            
            # Log stage output
            stage_output = StageOutput(
                stage_id="INTAKE",
                status=StageStatus.COMPLETED if validated else StageStatus.FAILED,
                data={"raw_id": raw_id, "ingest_ts": ingest_ts, "validated": validated},
                tool_selections={"storage": storage_selection.selected_tool}
            )
            state.stage_outputs.append(stage_output)
            
            logger.info("stage_completed", stage="INTAKE", validated=validated)
            
            return {
                "raw_id": raw_id,
                "ingest_ts": ingest_ts,
                "validated": validated,
                "current_stage": "UNDERSTAND",
                "status": WorkflowStatus.IN_PROGRESS,
                "bigtool_selections": state.bigtool_selections,
                "mcp_server_calls": state.mcp_server_calls,
                "stage_outputs": state.stage_outputs
            }
            
        except Exception as e:
            logger.error("stage_failed", stage="INTAKE", error=str(e))
            state.errors.append(f"INTAKE failed: {str(e)}")
            raise
    
    # ========== Stage 2: UNDERSTAND ==========
    def stage_understand(self, state: WorkflowState) -> Dict[str, Any]:
        """OCR extraction and line item parsing"""
        logger.info("stage_started", stage="UNDERSTAND", workflow_id=state.workflow_id)
        
        try:
            # Select OCR tool
            ocr_selection = self.bigtool.select(
                "ocr",
                {
                    "environment": os.getenv("ENVIRONMENT", "development"),
                    "document_quality": 0.8
                }
            )
            
            # Extract text using MCP ATLAS server
            ocr_result = self.mcp_client.execute_ability(
                MCPAbility.OCR_EXTRACT,
                {
                    "attachments": state.invoice_payload.attachments if state.invoice_payload else [],
                    "ocr_tool": ocr_selection.selected_tool
                },
                {"workflow_id": state.workflow_id, "stage": "UNDERSTAND"}
            )
            
            ocr_data = ocr_result.get("data", {})
            
            # Track selections
            state.bigtool_selections["UNDERSTAND_ocr"] = ocr_selection.selected_tool
            state.mcp_server_calls.append({
                "stage": "UNDERSTAND",
                "ability": "ocr_extract",
                "server": "ATLAS",
                "timestamp": datetime.utcnow().isoformat()
            })
            
            stage_output = StageOutput(
                stage_id="UNDERSTAND",
                status=StageStatus.COMPLETED,
                data=ocr_data,
                tool_selections={"ocr": ocr_selection.selected_tool}
            )
            state.stage_outputs.append(stage_output)
            
            logger.info("stage_completed", stage="UNDERSTAND")
            
            return {
                "parsed_invoice": ocr_data,
                "invoice_text": ocr_data.get("invoice_text"),
                "parsed_line_items": ocr_data.get("parsed_line_items", []),
                "detected_pos": ocr_data.get("detected_pos", []),
                "current_stage": "PREPARE",
                "bigtool_selections": state.bigtool_selections,
                "mcp_server_calls": state.mcp_server_calls,
                "stage_outputs": state.stage_outputs
            }
            
        except Exception as e:
            logger.error("stage_failed", stage="UNDERSTAND", error=str(e))
            state.errors.append(f"UNDERSTAND failed: {str(e)}")
            raise
    
    # ========== Stage 3: PREPARE ==========
    def stage_prepare(self, state: WorkflowState) -> Dict[str, Any]:
        """Normalize vendor and enrich profile"""
        logger.info("stage_started", stage="PREPARE", workflow_id=state.workflow_id)
        
        try:
            vendor_name = state.invoice_payload.vendor_name if state.invoice_payload else ""
            
            # Normalize vendor using COMMON server
            normalize_result = self.mcp_client.execute_ability(
                MCPAbility.NORMALIZE_VENDOR,
                {"vendor_name": vendor_name},
                {"workflow_id": state.workflow_id, "stage": "PREPARE"}
            )
            
            # Select enrichment tool
            enrichment_selection = self.bigtool.select(
                "enrichment",
                {"environment": os.getenv("ENVIRONMENT", "development")}
            )
            
            # Enrich vendor using ATLAS server
            enrich_result = self.mcp_client.execute_ability(
                MCPAbility.ENRICH_VENDOR,
                {
                    "vendor_name": normalize_result.get("data", {}).get("normalized_name", vendor_name),
                    "vendor_tax_id": state.invoice_payload.vendor_tax_id if state.invoice_payload else None,
                    "enrichment_tool": enrichment_selection.selected_tool
                },
                {"workflow_id": state.workflow_id, "stage": "PREPARE"}
            )
            
            # Compute flags using COMMON server
            flags_result = self.mcp_client.execute_ability(
                MCPAbility.COMPUTE_FLAGS,
                {
                    "invoice": state.invoice_payload.dict() if state.invoice_payload else {},
                    "vendor_profile": enrich_result.get("data", {})
                },
                {"workflow_id": state.workflow_id, "stage": "PREPARE"}
            )
            
            # Build vendor profile
            from ..models.state import VendorProfile
            vendor_profile = VendorProfile(
                normalized_name=normalize_result.get("data", {}).get("normalized_name", vendor_name),
                tax_id=enrich_result.get("data", {}).get("tax_id"),
                risk_score=enrich_result.get("data", {}).get("risk_score", 0.0),
                credit_score=enrich_result.get("data", {}).get("credit_score"),
                enrichment_meta=enrich_result.get("data", {}).get("enrichment_meta", {})
            )
            
            # Track selections
            state.bigtool_selections["PREPARE_enrichment"] = enrichment_selection.selected_tool
            state.mcp_server_calls.extend([
                {"stage": "PREPARE", "ability": "normalize_vendor", "server": "COMMON", "timestamp": datetime.utcnow().isoformat()},
                {"stage": "PREPARE", "ability": "enrich_vendor", "server": "ATLAS", "timestamp": datetime.utcnow().isoformat()},
                {"stage": "PREPARE", "ability": "compute_flags", "server": "COMMON", "timestamp": datetime.utcnow().isoformat()}
            ])
            
            stage_output = StageOutput(
                stage_id="PREPARE",
                status=StageStatus.COMPLETED,
                data={
                    "vendor_profile": vendor_profile.dict(),
                    "flags": flags_result.get("data", {})
                },
                tool_selections={"enrichment": enrichment_selection.selected_tool}
            )
            state.stage_outputs.append(stage_output)
            
            logger.info("stage_completed", stage="PREPARE")
            
            return {
                "vendor_profile": vendor_profile,
                "flags": flags_result.get("data", {}),
                "current_stage": "RETRIEVE",
                "bigtool_selections": state.bigtool_selections,
                "mcp_server_calls": state.mcp_server_calls,
                "stage_outputs": state.stage_outputs
            }
            
        except Exception as e:
            logger.error("stage_failed", stage="PREPARE", error=str(e))
            state.errors.append(f"PREPARE failed: {str(e)}")
            raise
    
    # ========== Stage 4: RETRIEVE ==========
    def stage_retrieve(self, state: WorkflowState) -> Dict[str, Any]:
        """Fetch POs, GRNs, and history from ERP"""
        logger.info("stage_started", stage="RETRIEVE", workflow_id=state.workflow_id)
        
        try:
            # Select ERP connector
            erp_selection = self.bigtool.select(
                "erp_connector",
                {"environment": os.getenv("ENVIRONMENT", "development")}
            )
            
            # Get PO reference
            po_reference = None
            if state.detected_pos:
                po_reference = state.detected_pos[0]
            elif state.invoice_payload and state.invoice_payload.po_reference:
                po_reference = state.invoice_payload.po_reference
            
            # Fetch PO using ATLAS
            po_result = self.mcp_client.execute_ability(
                MCPAbility.FETCH_PO,
                {
                    "po_reference": po_reference,
                    "erp_tool": erp_selection.selected_tool
                },
                {"workflow_id": state.workflow_id, "stage": "RETRIEVE"}
            )
            
            # Fetch GRN using ATLAS
            grn_result = self.mcp_client.execute_ability(
                MCPAbility.FETCH_GRN,
                {
                    "po_reference": po_reference,
                    "erp_tool": erp_selection.selected_tool
                },
                {"workflow_id": state.workflow_id, "stage": "RETRIEVE"}
            )
            
            # Fetch history using ATLAS
            history_result = self.mcp_client.execute_ability(
                MCPAbility.FETCH_HISTORY,
                {
                    "vendor_name": state.vendor_profile.normalized_name if state.vendor_profile else "",
                    "erp_tool": erp_selection.selected_tool
                },
                {"workflow_id": state.workflow_id, "stage": "RETRIEVE"}
            )
            
            # Track selections
            state.bigtool_selections["RETRIEVE_erp"] = erp_selection.selected_tool
            state.mcp_server_calls.extend([
                {"stage": "RETRIEVE", "ability": "fetch_po", "server": "ATLAS", "timestamp": datetime.utcnow().isoformat()},
                {"stage": "RETRIEVE", "ability": "fetch_grn", "server": "ATLAS", "timestamp": datetime.utcnow().isoformat()},
                {"stage": "RETRIEVE", "ability": "fetch_history", "server": "ATLAS", "timestamp": datetime.utcnow().isoformat()}
            ])
            
            matched_pos = po_result.get("data", {}).get("matched_pos", [])
            
            stage_output = StageOutput(
                stage_id="RETRIEVE",
                status=StageStatus.COMPLETED,
                data={
                    "matched_pos": matched_pos,
                    "matched_grns": grn_result.get("data", {}).get("matched_grns", []),
                    "history": history_result.get("data", {}).get("history", [])
                },
                tool_selections={"erp_connector": erp_selection.selected_tool}
            )
            state.stage_outputs.append(stage_output)
            
            logger.info("stage_completed", stage="RETRIEVE", pos_found=len(matched_pos))
            
            return {
                "matched_pos": matched_pos,
                "matched_grns": grn_result.get("data", {}).get("matched_grns", []),
                "history": history_result.get("data", {}).get("history", []),
                "current_stage": "MATCH_TWO_WAY",
                "bigtool_selections": state.bigtool_selections,
                "mcp_server_calls": state.mcp_server_calls,
                "stage_outputs": state.stage_outputs
            }
            
        except Exception as e:
            logger.error("stage_failed", stage="RETRIEVE", error=str(e))
            state.errors.append(f"RETRIEVE failed: {str(e)}")
            raise
    
    # ========== Stage 5: MATCH_TWO_WAY ==========
    def stage_match_two_way(self, state: WorkflowState) -> Dict[str, Any]:
        """Perform 2-way matching between invoice and PO"""
        logger.info("stage_started", stage="MATCH_TWO_WAY", workflow_id=state.workflow_id)
        
        try:
            # Get first PO if available
            po = state.matched_pos[0] if state.matched_pos else None
            
            # Compute match score using COMMON server
            match_result = self.mcp_client.execute_ability(
                MCPAbility.COMPUTE_MATCH_SCORE,
                {
                    "invoice": state.invoice_payload.dict() if state.invoice_payload else {},
                    "po": po,
                    "match_threshold": float(os.getenv("MATCH_THRESHOLD", "0.90")),
                    "tolerance_pct": float(os.getenv("TWO_WAY_TOLERANCE_PCT", "5"))
                },
                {"workflow_id": state.workflow_id, "stage": "MATCH_TWO_WAY"}
            )
            
            match_data = match_result.get("data", {})
            
            # Track MCP call
            state.mcp_server_calls.append({
                "stage": "MATCH_TWO_WAY",
                "ability": "compute_match_score",
                "server": "COMMON",
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Build match evidence
            from ..models.state import MatchEvidence
            match_evidence = MatchEvidence(**match_data.get("match_evidence", {}))
            
            stage_output = StageOutput(
                stage_id="MATCH_TWO_WAY",
                status=StageStatus.COMPLETED,
                data=match_data
            )
            state.stage_outputs.append(stage_output)
            
            logger.info(
                "stage_completed",
                stage="MATCH_TWO_WAY",
                match_result=match_data.get("match_result"),
                match_score=match_data.get("match_score")
            )
            
            return {
                "match_score": match_data.get("match_score", 0.0),
                "match_result": match_data.get("match_result", "PENDING"),
                "tolerance_pct": match_data.get("tolerance_pct", 0.0),
                "match_evidence": match_evidence,
                "current_stage": "CHECKPOINT_HITL" if match_data.get("match_result") == "FAILED" else "RECONCILE",
                "requires_human_review": match_data.get("match_result") == "FAILED",
                "mcp_server_calls": state.mcp_server_calls,
                "stage_outputs": state.stage_outputs
            }
            
        except Exception as e:
            logger.error("stage_failed", stage="MATCH_TWO_WAY", error=str(e))
            state.errors.append(f"MATCH_TWO_WAY failed: {str(e)}")
            raise
    
    # ========== Stage 6: CHECKPOINT_HITL ==========
    def stage_checkpoint_hitl(self, state: WorkflowState) -> Dict[str, Any]:
        """Create checkpoint for human review"""
        logger.info("stage_started", stage="CHECKPOINT_HITL", workflow_id=state.workflow_id)
        
        try:
            # Create checkpoint in database
            db = SessionLocal()
            checkpoint_repo = CheckpointRepository(db)
            
            reason = f"Match score {state.match_score:.2f} below threshold. Discrepancy: ${state.match_evidence.discrepancy:.2f}"
            
            checkpoint = checkpoint_repo.create_checkpoint(
                workflow_state=state,
                reason_for_hold=reason,
                priority=3 if state.match_score < 0.5 else 5
            )
            
            db.close()
            
            # Track checkpoint creation
            state.mcp_server_calls.append({
                "stage": "CHECKPOINT_HITL",
                "ability": "create_checkpoint",
                "server": "COMMON",
                "timestamp": datetime.utcnow().isoformat()
            })
            
            stage_output = StageOutput(
                stage_id="CHECKPOINT_HITL",
                status=StageStatus.COMPLETED,
                data={
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "review_url": checkpoint.review_url,
                    "paused_reason": checkpoint.reason_for_hold
                }
            )
            state.stage_outputs.append(stage_output)
            
            logger.info(
                "stage_completed",
                stage="CHECKPOINT_HITL",
                checkpoint_id=checkpoint.checkpoint_id
            )
            
            return {
                "hitl_checkpoint_id": checkpoint.checkpoint_id,
                "review_url": checkpoint.review_url,
                "paused_reason": checkpoint.reason_for_hold,
                "current_stage": "HITL_DECISION",
                "status": WorkflowStatus.AWAITING_HUMAN,
                "mcp_server_calls": state.mcp_server_calls,
                "stage_outputs": state.stage_outputs
            }
            
        except Exception as e:
            logger.error("stage_failed", stage="CHECKPOINT_HITL", error=str(e))
            state.errors.append(f"CHECKPOINT_HITL failed: {str(e)}")
            raise
    
    # ========== Stage 7: HITL_DECISION (continued in next file due to length) ==========
    def stage_hitl_decision(self, state: WorkflowState) -> Dict[str, Any]:
        """Process human review decision"""
        logger.info("stage_started", stage="HITL_DECISION", workflow_id=state.workflow_id)
        
        # This stage is triggered after human makes a decision via API
        # The state will already have human_decision populated
        
        try:
            decision = state.human_decision
            
            if not decision:
                # Wait for human decision - this shouldn't happen in normal flow
                logger.warning("hitl_awaiting_decision", checkpoint_id=state.hitl_checkpoint_id)
                return {
                    "current_stage": "HITL_DECISION",
                    "status": WorkflowStatus.AWAITING_HUMAN
                }
            
            # Mark checkpoint as resumed
            if state.hitl_checkpoint_id:
                db = SessionLocal()
                checkpoint_repo = CheckpointRepository(db)
                checkpoint_repo.mark_checkpoint_resumed(state.hitl_checkpoint_id)
                db.close()
            
            # Determine next stage
            if decision == HumanDecision.ACCEPT:
                next_stage = "RECONCILE"
                workflow_status = WorkflowStatus.IN_PROGRESS
            else:
                next_stage = "COMPLETE"
                workflow_status = WorkflowStatus.MANUAL_HANDOFF
            
            stage_output = StageOutput(
                stage_id="HITL_DECISION",
                status=StageStatus.COMPLETED,
                data={
                    "decision": decision,
                    "reviewer_id": state.reviewer_id,
                    "next_stage": next_stage
                }
            )
            state.stage_outputs.append(stage_output)
            
            logger.info(
                "stage_completed",
                stage="HITL_DECISION",
                decision=decision,
                next_stage=next_stage
            )
            
            return {
                "next_stage": next_stage,
                "current_stage": next_stage,
                "status": workflow_status,
                "stage_outputs": state.stage_outputs
            }
            
        except Exception as e:
            logger.error("stage_failed", stage="HITL_DECISION", error=str(e))
            state.errors.append(f"HITL_DECISION failed: {str(e)}")
            raise
    
    # ========== Stage 8: RECONCILE ==========
    def stage_reconcile(self, state: WorkflowState) -> Dict[str, Any]:
        """Build accounting entries"""
        logger.info("stage_started", stage="RECONCILE", workflow_id=state.workflow_id)
        
        try:
            # Build accounting entries using COMMON server
            reconcile_result = self.mcp_client.execute_ability(
                MCPAbility.BUILD_ACCOUNTING_ENTRIES,
                {
                    "invoice": state.invoice_payload.dict() if state.invoice_payload else {},
                    "vendor_profile": state.vendor_profile.dict() if state.vendor_profile else {}
                },
                {"workflow_id": state.workflow_id, "stage": "RECONCILE"}
            )
            
            reconcile_data = reconcile_result.get("data", {})
            
            state.mcp_server_calls.append({
                "stage": "RECONCILE",
                "ability": "build_accounting_entries",
                "server": "COMMON",
                "timestamp": datetime.utcnow().isoformat()
            })
            
            stage_output = StageOutput(
                stage_id="RECONCILE",
                status=StageStatus.COMPLETED,
                data=reconcile_data
            )
            state.stage_outputs.append(stage_output)
            
            logger.info("stage_completed", stage="RECONCILE")
            
            return {
                "accounting_entries": reconcile_data.get("accounting_entries", []),
                "reconciliation_report": reconcile_data.get("reconciliation_report", {}),
                "current_stage": "APPROVE",
                "mcp_server_calls": state.mcp_server_calls,
                "stage_outputs": state.stage_outputs
            }
            
        except Exception as e:
            logger.error("stage_failed", stage="RECONCILE", error=str(e))
            state.errors.append(f"RECONCILE failed: {str(e)}")
            raise
    
    # ========== Remaining stages (APPROVE, POSTING, NOTIFY, COMPLETE) ==========
    # Implemented similarly to above stages...
    # For brevity, I'll include them in a condensed form:
    
    def stage_approve(self, state: WorkflowState) -> Dict[str, Any]:
        """Apply approval policy"""
        logger.info("stage_started", stage="APPROVE", workflow_id=state.workflow_id)
        
        try:
            approval_result = self.mcp_client.execute_ability(
                MCPAbility.APPLY_APPROVAL_POLICY,
                {
                    "amount": state.invoice_payload.amount if state.invoice_payload else 0,
                    "invoice_id": state.invoice_payload.invoice_id if state.invoice_payload else "",
                    "auto_approve_threshold": state.approval_amount_threshold
                },
                {"workflow_id": state.workflow_id, "stage": "APPROVE"}
            )
            
            approval_data = approval_result.get("data", {})
            
            return {
                "approval_status": approval_data.get("approval_status", "PENDING"),
                "approver_id": approval_data.get("approver_id"),
                "current_stage": "POSTING",
                "stage_outputs": state.stage_outputs + [StageOutput(stage_id="APPROVE", status=StageStatus.COMPLETED, data=approval_data)]
            }
        except Exception as e:
            logger.error("stage_failed", stage="APPROVE", error=str(e))
            raise
    
    def stage_posting(self, state: WorkflowState) -> Dict[str, Any]:
        """Post to ERP and schedule payment"""
        logger.info("stage_started", stage="POSTING", workflow_id=state.workflow_id)
        
        try:
            erp_selection = self.bigtool.select("erp_connector", {"environment": "development"})
            
            post_result = self.mcp_client.execute_ability(
                MCPAbility.POST_TO_ERP,
                {
                    "accounting_entries": state.accounting_entries,
                    "invoice_id": state.invoice_payload.invoice_id if state.invoice_payload else "",
                    "erp_tool": erp_selection.selected_tool
                },
                {"workflow_id": state.workflow_id, "stage": "POSTING"}
            )
            
            payment_result = self.mcp_client.execute_ability(
                MCPAbility.SCHEDULE_PAYMENT,
                {
                    "amount": state.invoice_payload.amount if state.invoice_payload else 0,
                    "due_date": state.invoice_payload.due_date if state.invoice_payload else "",
                    "invoice_id": state.invoice_payload.invoice_id if state.invoice_payload else ""
                },
                {"workflow_id": state.workflow_id, "stage": "POSTING"}
            )
            
            return {
                "posted": post_result.get("data", {}).get("posted", False),
                "erp_txn_id": post_result.get("data", {}).get("erp_txn_id"),
                "scheduled_payment_id": payment_result.get("data", {}).get("scheduled_payment_id"),
                "current_stage": "NOTIFY",
                "bigtool_selections": {**state.bigtool_selections, "POSTING_erp": erp_selection.selected_tool},
                "stage_outputs": state.stage_outputs + [StageOutput(stage_id="POSTING", status=StageStatus.COMPLETED, data=post_result.get("data", {}))]
            }
        except Exception as e:
            logger.error("stage_failed", stage="POSTING", error=str(e))
            raise
    
    def stage_notify(self, state: WorkflowState) -> Dict[str, Any]:
        """Send notifications"""
        logger.info("stage_started", stage="NOTIFY", workflow_id=state.workflow_id)
        
        try:
            email_selection = self.bigtool.select("email", {"environment": "development"})
            
            vendor_notify = self.mcp_client.execute_ability(
                MCPAbility.NOTIFY_VENDOR,
                {
                    "vendor_name": state.vendor_profile.normalized_name if state.vendor_profile else "",
                    "invoice_id": state.invoice_payload.invoice_id if state.invoice_payload else "",
                    "notification_tool": email_selection.selected_tool
                },
                {"workflow_id": state.workflow_id, "stage": "NOTIFY"}
            )
            
            finance_notify = self.mcp_client.execute_ability(
                MCPAbility.NOTIFY_FINANCE_TEAM,
                {
                    "invoice_id": state.invoice_payload.invoice_id if state.invoice_payload else "",
                    "status": "COMPLETED",
                    "notification_tool": email_selection.selected_tool
                },
                {"workflow_id": state.workflow_id, "stage": "NOTIFY"}
            )
            
            return {
                "notify_status": {"vendor": "sent", "finance": "sent"},
                "notified_parties": ["vendor", "finance_team"],
                "current_stage": "COMPLETE",
                "bigtool_selections": {**state.bigtool_selections, "NOTIFY_email": email_selection.selected_tool},
                "stage_outputs": state.stage_outputs + [StageOutput(stage_id="NOTIFY", status=StageStatus.COMPLETED, data={})]
            }
        except Exception as e:
            logger.error("stage_failed", stage="NOTIFY", error=str(e))
            raise
    
    def stage_complete(self, state: WorkflowState) -> Dict[str, Any]:
        """Finalize workflow"""
        logger.info("stage_started", stage="COMPLETE", workflow_id=state.workflow_id)
        
        try:
            final_payload = {
                "workflow_id": state.workflow_id,
                "invoice_id": state.invoice_payload.invoice_id if state.invoice_payload else "",
                "vendor": state.vendor_profile.normalized_name if state.vendor_profile else "",
                "amount": state.invoice_payload.amount if state.invoice_payload else 0,
                "status": state.status.value if hasattr(state.status, 'value') else state.status,
                "match_score": state.match_score,
                "posted": state.posted,
                "erp_txn_id": state.erp_txn_id,
                "completed_at": datetime.utcnow().isoformat()
            }
            
            # Build audit log
            audit_log = [
                {
                    "stage": output.stage_id,
                    "status": output.status.value if hasattr(output.status, 'value') else output.status,
                    "timestamp": output.timestamp.isoformat() if hasattr(output.timestamp, 'isoformat') else output.timestamp
                }
                for output in state.stage_outputs
            ]
            
            # Compare human_decision safely (could be string or enum)
            human_decision_value = state.human_decision.value if hasattr(state.human_decision, 'value') else state.human_decision
            final_status = WorkflowStatus.COMPLETED if human_decision_value != "REJECT" else WorkflowStatus.MANUAL_HANDOFF
            
            logger.info("stage_completed", stage="COMPLETE", final_status=final_status)
            
            return {
                "final_payload": final_payload,
                "audit_log": audit_log,
                "current_stage": "COMPLETE",
                "status": final_status,
                "stage_outputs": state.stage_outputs + [StageOutput(stage_id="COMPLETE", status=StageStatus.COMPLETED, data=final_payload)]
            }
        except Exception as e:
            logger.error("stage_failed", stage="COMPLETE", error=str(e))
            raise
    
    def execute(self, invoice_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the workflow for an invoice"""
        # Create initial state
        from ..models.state import InvoicePayload
        
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        
        initial_state = WorkflowState(
            workflow_id=workflow_id,
            invoice_payload=InvoicePayload(**invoice_payload)
        )
        
        logger.info("workflow_execution_started", workflow_id=workflow_id)
        
        # Execute workflow
        config = {"configurable": {"thread_id": workflow_id}}
        
        try:
            result = self.app.invoke(initial_state.dict(), config)
            logger.info("workflow_execution_completed", workflow_id=workflow_id)
            return result
        except Exception as e:
            logger.error("workflow_execution_failed", workflow_id=workflow_id, error=str(e))
            raise
    
    def resume(self, checkpoint_id: str, decision: str, reviewer_id: str, notes: Optional[str] = None) -> Dict[str, Any]:
        """Resume workflow from checkpoint after human decision"""
        logger.info("workflow_resume_requested", checkpoint_id=checkpoint_id, decision=decision)
        
        # Get checkpoint from database
        db = SessionLocal()
        checkpoint_repo = CheckpointRepository(db)
        
        # Update checkpoint with decision
        checkpoint = checkpoint_repo.update_checkpoint_with_decision(
            checkpoint_id=checkpoint_id,
            decision=HumanDecision(decision),
            reviewer_id=reviewer_id,
            notes=notes
        )
        
        if not checkpoint:
            db.close()
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")
        
        # Reconstruct state from checkpoint
        state_data = checkpoint.state_blob
        state_data["human_decision"] = decision
        state_data["reviewer_id"] = reviewer_id
        state_data["reviewer_notes"] = notes
        state_data["resume_token"] = checkpoint.resume_token
        
        db.close()
        
        # Resume execution from HITL_DECISION node
        config = {"configurable": {"thread_id": state_data["workflow_id"]}}
        
        try:
            result = self.app.invoke(state_data, config)
            logger.info("workflow_resumed", checkpoint_id=checkpoint_id)
            return result
        except Exception as e:
            logger.error("workflow_resume_failed", checkpoint_id=checkpoint_id, error=str(e))
            raise
