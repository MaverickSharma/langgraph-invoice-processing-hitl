"""
ATLAS Server - Mock implementation of ATLAS abilities
Handles operations requiring external system integration
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import random
import structlog

logger = structlog.get_logger()


def execute_atlas_ability(
    ability,
    payload: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Execute ATLAS server ability
    """
    ability_value = ability.value if hasattr(ability, 'value') else ability
    
    logger.info("executing_atlas_ability", ability=ability_value)
    
    # Route to appropriate handler
    handlers = {
        "ocr_extract": ocr_extract,
        "enrich_vendor": enrich_vendor,
        "fetch_po": fetch_po,
        "fetch_grn": fetch_grn,
        "fetch_history": fetch_history,
        "apply_approval_policy": apply_approval_policy,
        "post_to_erp": post_to_erp,
        "schedule_payment": schedule_payment,
        "notify_vendor": notify_vendor,
        "notify_finance_team": notify_finance_team,
    }
    
    handler = handlers.get(ability_value)
    if not handler:
        return {"success": False, "error": f"Unknown ability: {ability_value}"}
    
    try:
        result = handler(payload, context)
        return {"success": True, "data": result, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("ability_execution_failed", ability=ability_value, error=str(e))
        return {"success": False, "error": str(e)}


def ocr_extract(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract text from invoice attachments using OCR"""
    attachments = payload.get("attachments", [])
    ocr_tool = payload.get("ocr_tool", "tesseract")
    
    # Mock OCR extraction
    extracted_text = f"""
    INVOICE
    
    Invoice Number: INV-2024-001
    Date: 2024-12-15
    Due Date: 2025-01-15
    
    Bill To:
    Your Company Inc
    123 Main Street
    
    From:
    Acme Corporation
    Tax ID: 12-3456789
    
    Description                 Qty    Unit Price    Total
    ----------------------------------------------------------
    Product A                   10     $100.00       $1,000.00
    Product B                   5      $200.00       $1,000.00
    Consulting Services         1      $3,000.00     $3,000.00
    
    Subtotal:                                        $5,000.00
    Tax (10%):                                       $500.00
    ----------------------------------------------------------
    TOTAL:                                           $5,500.00
    
    Payment Terms: Net 30
    PO Reference: PO-2024-456
    """
    
    # Parse line items from OCR text
    line_items = [
        {"desc": "Product A", "qty": 10, "unit_price": 100.00, "total": 1000.00},
        {"desc": "Product B", "qty": 5, "unit_price": 200.00, "total": 1000.00},
        {"desc": "Consulting Services", "qty": 1, "unit_price": 3000.00, "total": 3000.00}
    ]
    
    return {
        "invoice_text": extracted_text,
        "parsed_line_items": line_items,
        "detected_pos": ["PO-2024-456"],
        "currency": "USD",
        "parsed_dates": {
            "invoice_date": "2024-12-15",
            "due_date": "2025-01-15"
        },
        "ocr_confidence": 0.95,
        "ocr_tool_used": ocr_tool,
        "extracted_at": datetime.utcnow().isoformat()
    }


def enrich_vendor(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Enrich vendor profile with external data"""
    vendor_name = payload.get("vendor_name", "")
    vendor_tax_id = payload.get("vendor_tax_id")
    enrichment_tool = payload.get("enrichment_tool", "vendor_db")
    
    # Mock enrichment data
    enrichment_meta = {
        "company_size": "Medium",
        "industry": "Technology",
        "country": "United States",
        "state": "California",
        "employees": "50-200",
        "founded_year": 2010,
        "website": "www.acmecorp.com",
        "credit_rating": "A",
        "payment_history_score": 0.92,
        "enrichment_source": enrichment_tool,
        "enriched_at": datetime.utcnow().isoformat()
    }
    
    # Calculate credit score
    credit_score = 750 + random.randint(-50, 50)
    
    # Calculate risk score based on credit
    if credit_score >= 750:
        risk_score = 0.1
    elif credit_score >= 650:
        risk_score = 0.3
    elif credit_score >= 550:
        risk_score = 0.5
    else:
        risk_score = 0.8
    
    return {
        "tax_id": vendor_tax_id or "12-3456789",
        "credit_score": credit_score,
        "risk_score": risk_score,
        "enrichment_meta": enrichment_meta
    }


def fetch_po(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Fetch Purchase Orders from ERP"""
    po_reference = payload.get("po_reference")
    erp_tool = payload.get("erp_tool", "mock_erp")
    
    # Mock PO data
    # Randomly decide if PO matches or has discrepancy
    has_discrepancy = random.random() < 0.3  # 30% chance of discrepancy
    
    if po_reference and not has_discrepancy:
        # Good match
        po = {
            "po_number": po_reference,
            "vendor": "ACME CORP",
            "amount": 5500.00,  # Matches invoice
            "currency": "USD",
            "status": "APPROVED",
            "created_date": "2024-11-15",
            "line_items": [
                {"desc": "Product A", "qty": 10, "unit_price": 100.00, "total": 1000.00},
                {"desc": "Product B", "qty": 5, "unit_price": 200.00, "total": 1000.00},
                {"desc": "Consulting Services", "qty": 1, "unit_price": 3000.00, "total": 3000.00}
            ]
        }
    elif po_reference and has_discrepancy:
        # Mismatch - will trigger HITL
        po = {
            "po_number": po_reference,
            "vendor": "ACME CORP",
            "amount": 4800.00,  # Doesn't match invoice (5500)
            "currency": "USD",
            "status": "APPROVED",
            "created_date": "2024-11-15",
            "line_items": [
                {"desc": "Product A", "qty": 10, "unit_price": 100.00, "total": 1000.00},
                {"desc": "Product B", "qty": 5, "unit_price": 200.00, "total": 1000.00}
                # Missing consulting services line
            ]
        }
    else:
        # No PO found
        po = None
    
    return {
        "matched_pos": [po] if po else [],
        "erp_system": erp_tool,
        "fetched_at": datetime.utcnow().isoformat()
    }


def fetch_grn(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Fetch Goods Received Notes from ERP"""
    po_reference = payload.get("po_reference")
    erp_tool = payload.get("erp_tool", "mock_erp")
    
    # Mock GRN data
    grns = []
    if po_reference:
        grns = [
            {
                "grn_number": f"GRN-{po_reference[-3:]}",
                "po_reference": po_reference,
                "received_date": "2024-12-01",
                "received_qty": 15,
                "status": "COMPLETED"
            }
        ]
    
    return {
        "matched_grns": grns,
        "erp_system": erp_tool,
        "fetched_at": datetime.utcnow().isoformat()
    }


def fetch_history(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Fetch historical invoices for vendor"""
    vendor_name = payload.get("vendor_name")
    erp_tool = payload.get("erp_tool", "mock_erp")
    
    # Mock historical data
    history = [
        {
            "invoice_id": "INV-2024-000",
            "date": "2024-10-15",
            "amount": 4500.00,
            "status": "PAID",
            "payment_date": "2024-11-10"
        },
        {
            "invoice_id": "INV-2024-002",
            "date": "2024-09-20",
            "amount": 3200.00,
            "status": "PAID",
            "payment_date": "2024-10-15"
        }
    ]
    
    return {
        "history": history,
        "vendor_name": vendor_name,
        "erp_system": erp_tool,
        "fetched_at": datetime.utcnow().isoformat()
    }


def apply_approval_policy(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply approval policy based on invoice amount and rules"""
    amount = payload.get("amount", 0)
    invoice_id = payload.get("invoice_id")
    
    # Auto-approval threshold
    auto_approve_threshold = payload.get("auto_approve_threshold", 10000)
    
    if amount <= auto_approve_threshold:
        approval_status = "AUTO_APPROVED"
        approver_id = "system"
    else:
        approval_status = "REQUIRES_APPROVAL"
        approver_id = "finance_manager"
    
    return {
        "approval_status": approval_status,
        "approver_id": approver_id,
        "approval_threshold": auto_approve_threshold,
        "invoice_amount": amount,
        "policy_applied": "amount_based_approval",
        "applied_at": datetime.utcnow().isoformat()
    }


def post_to_erp(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Post accounting entries to ERP"""
    entries = payload.get("accounting_entries", [])
    invoice_id = payload.get("invoice_id")
    erp_tool = payload.get("erp_tool", "mock_erp")
    
    # Mock ERP posting
    erp_txn_id = f"ERP-TXN-{random.randint(10000, 99999)}"
    
    return {
        "posted": True,
        "erp_txn_id": erp_txn_id,
        "entry_count": len(entries),
        "erp_system": erp_tool,
        "posted_at": datetime.utcnow().isoformat()
    }


def schedule_payment(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Schedule payment for invoice"""
    amount = payload.get("amount", 0)
    due_date = payload.get("due_date")
    invoice_id = payload.get("invoice_id")
    
    # Mock payment scheduling
    scheduled_payment_id = f"PAY-{random.randint(10000, 99999)}"
    
    return {
        "scheduled_payment_id": scheduled_payment_id,
        "amount": amount,
        "scheduled_date": due_date or (datetime.utcnow() + timedelta(days=30)).isoformat(),
        "payment_method": "ACH",
        "status": "SCHEDULED",
        "scheduled_at": datetime.utcnow().isoformat()
    }


def notify_vendor(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Send notification to vendor"""
    vendor_name = payload.get("vendor_name")
    invoice_id = payload.get("invoice_id")
    notification_tool = payload.get("notification_tool", "ses")
    
    # Mock notification
    notification_id = f"NOTIF-{random.randint(10000, 99999)}"
    
    return {
        "notification_id": notification_id,
        "recipient": vendor_name,
        "channel": "email",
        "status": "SENT",
        "subject": f"Invoice {invoice_id} Processed",
        "notification_tool": notification_tool,
        "sent_at": datetime.utcnow().isoformat()
    }


def notify_finance_team(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Send notification to internal finance team"""
    invoice_id = payload.get("invoice_id")
    status = payload.get("status", "COMPLETED")
    notification_tool = payload.get("notification_tool", "ses")
    
    # Mock notification
    notification_id = f"NOTIF-{random.randint(10000, 99999)}"
    
    return {
        "notification_id": notification_id,
        "recipients": ["finance@company.com", "ap@company.com"],
        "channel": "email",
        "status": "SENT",
        "subject": f"Invoice {invoice_id} - Status: {status}",
        "notification_tool": notification_tool,
        "sent_at": datetime.utcnow().isoformat()
    }
