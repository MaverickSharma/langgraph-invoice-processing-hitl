"""
Flask API Server for Invoice Processing Workflow
Provides REST endpoints for workflow execution and human review
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import structlog
from datetime import datetime
import os
from dotenv import load_dotenv

from src.agents.workflow_engine import InvoiceProcessingWorkflow
from src.database.db import SessionLocal, init_db
from src.database.checkpoint_repo import CheckpointRepository
from src.models.checkpoint import ReviewDecisionRequest, HumanDecision

load_dotenv()

# Configure structlog
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger()

# Initialize Flask app
app = Flask(__name__, static_folder='static')
CORS(app)

# Initialize workflow engine
workflow_engine = InvoiceProcessingWorkflow()

# Initialize database
init_db()

logger.info("flask_app_initialized")


@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('static', 'index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "invoice-processing-workflow"
    })


@app.route('/api/workflow/execute', methods=['POST'])
def execute_workflow():
    """
    Execute invoice processing workflow
    
    Request body:
    {
        "invoice_payload": {
            "invoice_id": "INV-2024-001",
            "vendor_name": "Acme Corp",
            "amount": 5500,
            ...
        }
    }
    """
    try:
        data = request.get_json()
        invoice_payload = data.get('invoice_payload')
        
        if not invoice_payload:
            return jsonify({"error": "invoice_payload is required"}), 400
        
        logger.info("workflow_execution_requested", invoice_id=invoice_payload.get('invoice_id'))
        
        # Execute workflow
        result = workflow_engine.execute(invoice_payload)
        
        logger.info("workflow_execution_response_sent", workflow_id=result.get('workflow_id'))
        
        return jsonify({
            "success": True,
            "workflow_id": result.get('workflow_id'),
            "status": result.get('status'),
            "current_stage": result.get('current_stage'),
            "requires_human_review": result.get('requires_human_review', False),
            "checkpoint_id": result.get('checkpoint_id'),
            "review_url": result.get('review_url'),
            "final_payload": result.get('final_payload'),
            "message": "Workflow executed successfully"
        }), 200
        
    except Exception as e:
        logger.error("workflow_execution_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/workflow/status/<workflow_id>', methods=['GET'])
def get_workflow_status(workflow_id):
    """Get workflow status"""
    try:
        # In production, query from database
        return jsonify({
            "workflow_id": workflow_id,
            "status": "IN_PROGRESS",
            "current_stage": "UNDERSTAND",
            "message": "Workflow status retrieved"
        }), 200
    except Exception as e:
        logger.error("get_workflow_status_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/human-review/pending', methods=['GET'])
def get_pending_reviews():
    """
    Get all pending human review items
    
    Response:
    {
        "items": [
            {
                "checkpoint_id": "chk_123",
                "invoice_id": "INV-2024-001",
                "vendor_name": "Acme Corp",
                "amount": 5500,
                "created_at": "2024-12-31T...",
                "reason_for_hold": "Match score below threshold",
                "review_url": "/human-review/review/chk_123"
            }
        ]
    }
    """
    try:
        db = SessionLocal()
        checkpoint_repo = CheckpointRepository(db)
        
        pending_reviews = checkpoint_repo.get_pending_reviews()
        
        db.close()
        
        items = [
            {
                "checkpoint_id": review.checkpoint_id,
                "workflow_id": review.workflow_id,
                "invoice_id": review.invoice_id,
                "vendor_name": review.vendor_name,
                "amount": review.amount,
                "currency": review.currency,
                "created_at": review.created_at.isoformat(),
                "reason_for_hold": review.reason_for_hold,
                "review_url": review.review_url,
                "priority": review.priority
            }
            for review in pending_reviews
        ]
        
        logger.info("pending_reviews_retrieved", count=len(items))
        
        return jsonify({"items": items}), 200
        
    except Exception as e:
        logger.error("get_pending_reviews_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/human-review/checkpoint/<checkpoint_id>', methods=['GET'])
def get_checkpoint_details(checkpoint_id):
    """Get detailed checkpoint information for review"""
    try:
        db = SessionLocal()
        checkpoint_repo = CheckpointRepository(db)
        
        checkpoint = checkpoint_repo.get_checkpoint(checkpoint_id)
        
        db.close()
        
        if not checkpoint:
            return jsonify({"error": "Checkpoint not found"}), 404
        
        # Extract relevant information from state
        state = checkpoint.state_blob
        
        return jsonify({
            "checkpoint_id": checkpoint.checkpoint_id,
            "workflow_id": checkpoint.workflow_id,
            "invoice_id": checkpoint.invoice_id,
            "vendor_name": checkpoint.vendor_name,
            "amount": checkpoint.amount,
            "currency": checkpoint.currency,
            "match_score": checkpoint.match_score,
            "reason_for_hold": checkpoint.reason_for_hold,
            "discrepancy_details": checkpoint.discrepancy_details,
            "invoice_payload": state.get("invoice_payload"),
            "vendor_profile": state.get("vendor_profile"),
            "matched_pos": state.get("matched_pos", []),
            "match_evidence": state.get("match_evidence"),
            "created_at": checkpoint.created_at.isoformat(),
            "status": checkpoint.status
        }), 200
        
    except Exception as e:
        logger.error("get_checkpoint_details_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/human-review/decision', methods=['POST'])
def submit_review_decision():
    """
    Submit human review decision and resume workflow
    
    Request body:
    {
        "checkpoint_id": "chk_123",
        "decision": "ACCEPT",
        "notes": "Verified with vendor",
        "reviewer_id": "john.doe@company.com"
    }
    
    Response:
    {
        "checkpoint_id": "chk_123",
        "resume_token": "resume_xyz",
        "next_stage": "RECONCILE",
        "message": "Decision recorded and workflow resumed"
    }
    """
    try:
        data = request.get_json()
        
        checkpoint_id = data.get('checkpoint_id')
        decision = data.get('decision')
        notes = data.get('notes')
        reviewer_id = data.get('reviewer_id')
        
        if not all([checkpoint_id, decision, reviewer_id]):
            return jsonify({"error": "checkpoint_id, decision, and reviewer_id are required"}), 400
        
        if decision not in [d.value for d in HumanDecision]:
            return jsonify({"error": f"Invalid decision. Must be one of: {[d.value for d in HumanDecision]}"}), 400
        
        logger.info(
            "review_decision_submitted",
            checkpoint_id=checkpoint_id,
            decision=decision,
            reviewer_id=reviewer_id
        )
        
        # Resume workflow with decision
        result = workflow_engine.resume(
            checkpoint_id=checkpoint_id,
            decision=decision,
            reviewer_id=reviewer_id,
            notes=notes
        )
        
        logger.info("workflow_resumed_after_decision", checkpoint_id=checkpoint_id)
        
        return jsonify({
            "checkpoint_id": checkpoint_id,
            "resume_token": result.get('resume_token'),
            "next_stage": result.get('next_stage'),
            "workflow_status": result.get('status'),
            "message": "Decision recorded and workflow resumed successfully"
        }), 200
        
    except Exception as e:
        logger.error("submit_review_decision_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/bigtool/selections/<workflow_id>', methods=['GET'])
def get_bigtool_selections(workflow_id):
    """Get bigtool selections for a workflow"""
    try:
        # In production, query from database
        return jsonify({
            "workflow_id": workflow_id,
            "selections": {
                "INTAKE_storage": "sqlite",
                "UNDERSTAND_ocr": "tesseract",
                "PREPARE_enrichment": "vendor_db",
                "RETRIEVE_erp": "mock_erp",
                "POSTING_erp": "mock_erp",
                "NOTIFY_email": "ses"
            }
        }), 200
    except Exception as e:
        logger.error("get_bigtool_selections_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/mcp/calls/<workflow_id>', methods=['GET'])
def get_mcp_calls(workflow_id):
    """Get MCP server calls for a workflow"""
    try:
        # In production, query from database
        return jsonify({
            "workflow_id": workflow_id,
            "mcp_calls": [
                {"stage": "INTAKE", "ability": "validate_schema", "server": "COMMON"},
                {"stage": "UNDERSTAND", "ability": "ocr_extract", "server": "ATLAS"},
                {"stage": "PREPARE", "ability": "normalize_vendor", "server": "COMMON"},
                {"stage": "PREPARE", "ability": "enrich_vendor", "server": "ATLAS"}
            ]
        }), 200
    except Exception as e:
        logger.error("get_mcp_calls_error", error=str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('API_PORT', 5000))
    host = os.getenv('API_HOST', '0.0.0.0')
    
    logger.info("starting_flask_server", host=host, port=port)
    
    app.run(host=host, port=port, debug=True)
