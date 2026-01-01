"""
COMMON Server - Mock implementation of COMMON abilities
Handles operations that don't require external systems
"""
from typing import Dict, Any, Optional
import re
from datetime import datetime
import structlog

logger = structlog.get_logger()


def execute_common_ability(
    ability,
    payload: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Execute COMMON server ability
    """
    ability_value = ability.value if hasattr(ability, 'value') else ability
    
    logger.info("executing_common_ability", ability=ability_value)
    
    # Route to appropriate handler
    handlers = {
        "validate_schema": validate_schema,
        "normalize_vendor": normalize_vendor,
        "compute_flags": compute_flags,
        "compute_match_score": compute_match_score,
        "build_accounting_entries": build_accounting_entries,
        "persist_state": persist_state,
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


def validate_schema(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate invoice payload schema"""
    invoice = payload.get("invoice_payload", {})
    
    required_fields = ["invoice_id", "vendor_name", "amount", "currency", "invoice_date"]
    missing_fields = [field for field in required_fields if not invoice.get(field)]
    
    validation_errors = []
    
    if missing_fields:
        validation_errors.append(f"Missing required fields: {', '.join(missing_fields)}")
    
    # Validate amount
    if invoice.get("amount"):
        try:
            amount = float(invoice["amount"])
            if amount <= 0:
                validation_errors.append("Amount must be positive")
        except (ValueError, TypeError):
            validation_errors.append("Invalid amount format")
    
    # Validate date format
    if invoice.get("invoice_date"):
        try:
            datetime.fromisoformat(invoice["invoice_date"].replace("Z", "+00:00"))
        except ValueError:
            validation_errors.append("Invalid invoice_date format")
    
    is_valid = len(validation_errors) == 0
    
    return {
        "validated": is_valid,
        "validation_errors": validation_errors,
        "validated_at": datetime.utcnow().isoformat()
    }


def normalize_vendor(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize vendor name"""
    vendor_name = payload.get("vendor_name", "")
    
    # Normalize: uppercase, remove extra spaces, remove special chars
    normalized = vendor_name.upper().strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = re.sub(r'[^\w\s-]', '', normalized)
    
    # Common company suffix normalization
    suffixes = {
        "INCORPORATED": "INC",
        "CORPORATION": "CORP",
        "LIMITED": "LTD",
        "COMPANY": "CO",
        "LLC": "LLC",
        "LLP": "LLP"
    }
    
    for full, abbr in suffixes.items():
        normalized = normalized.replace(full, abbr)
    
    return {
        "original_name": vendor_name,
        "normalized_name": normalized,
        "normalization_rules_applied": ["uppercase", "trim_spaces", "suffix_normalization"]
    }


def compute_flags(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute validation and risk flags"""
    invoice = payload.get("invoice", {})
    vendor_profile = payload.get("vendor_profile", {})
    
    flags = {
        "missing_info": [],
        "risk_score": 0.0,
        "warnings": []
    }
    
    # Check for missing information
    if not invoice.get("po_reference"):
        flags["missing_info"].append("po_reference")
    
    if not vendor_profile.get("tax_id"):
        flags["missing_info"].append("vendor_tax_id")
        flags["risk_score"] += 0.2
    
    # Check amount threshold
    amount = invoice.get("amount", 0)
    if amount > 50000:
        flags["warnings"].append("high_value_transaction")
        flags["risk_score"] += 0.3
    
    # Check vendor enrichment
    if not vendor_profile.get("enrichment_meta"):
        flags["warnings"].append("vendor_not_enriched")
        flags["risk_score"] += 0.1
    
    # Normalize risk score to 0-1
    flags["risk_score"] = min(flags["risk_score"], 1.0)
    
    return flags


def compute_match_score(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute 2-way match score between invoice and PO"""
    invoice = payload.get("invoice", {})
    po = payload.get("po", {})
    threshold = payload.get("match_threshold", 0.90)
    tolerance_pct = payload.get("tolerance_pct", 5)
    
    if not po:
        # No PO found - match fails
        return {
            "match_score": 0.0,
            "match_result": "FAILED",
            "tolerance_pct": 0.0,
            "match_evidence": {
                "reason": "No PO found",
                "invoice_amount": invoice.get("amount", 0),
                "po_amount": None,
                "discrepancy": invoice.get("amount", 0)
            }
        }
    
    invoice_amount = float(invoice.get("amount", 0))
    po_amount = float(po.get("amount", 0))
    
    # Calculate discrepancy
    discrepancy = abs(invoice_amount - po_amount)
    discrepancy_pct = (discrepancy / po_amount * 100) if po_amount > 0 else 100
    
    # Calculate match score
    if discrepancy_pct <= tolerance_pct:
        match_score = 1.0 - (discrepancy_pct / (tolerance_pct * 2))
    else:
        match_score = max(0.0, 1.0 - (discrepancy_pct / 100))
    
    match_result = "MATCHED" if match_score >= threshold else "FAILED"
    
    # Check line items match
    invoice_items = invoice.get("line_items", [])
    po_items = po.get("line_items", [])
    
    discrepancy_items = []
    if len(invoice_items) != len(po_items):
        discrepancy_items.append(f"Line item count mismatch: Invoice has {len(invoice_items)}, PO has {len(po_items)}")
    
    return {
        "match_score": round(match_score, 3),
        "match_result": match_result,
        "tolerance_pct": round(discrepancy_pct, 2),
        "match_evidence": {
            "invoice_amount": invoice_amount,
            "po_amount": po_amount,
            "discrepancy": round(discrepancy, 2),
            "discrepancy_pct": round(discrepancy_pct, 2),
            "discrepancy_items": discrepancy_items,
            "po_number": po.get("po_number")
        }
    }


def build_accounting_entries(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build accounting journal entries"""
    invoice = payload.get("invoice", {})
    vendor = payload.get("vendor_profile", {})
    
    amount = float(invoice.get("amount", 0))
    currency = invoice.get("currency", "USD")
    invoice_id = invoice.get("invoice_id", "unknown")
    
    # Build journal entries
    entries = [
        {
            "entry_type": "debit",
            "account": "Accounts Payable",
            "account_code": "2000",
            "amount": amount,
            "currency": currency,
            "description": f"Invoice {invoice_id} - {vendor.get('normalized_name', 'Unknown Vendor')}"
        },
        {
            "entry_type": "credit",
            "account": "Cash",
            "account_code": "1000",
            "amount": amount,
            "currency": currency,
            "description": f"Payment for Invoice {invoice_id}"
        }
    ]
    
    reconciliation_report = {
        "invoice_id": invoice_id,
        "vendor": vendor.get("normalized_name"),
        "total_amount": amount,
        "currency": currency,
        "entry_count": len(entries),
        "balanced": True,  # Debit equals Credit
        "created_at": datetime.utcnow().isoformat()
    }
    
    return {
        "accounting_entries": entries,
        "reconciliation_report": reconciliation_report
    }


def persist_state(payload: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Persist workflow state (mock)"""
    workflow_id = payload.get("workflow_id")
    state = payload.get("state", {})
    
    # In production, save to database
    # For demo, just return success
    
    return {
        "persisted": True,
        "workflow_id": workflow_id,
        "state_size": len(str(state)),
        "persisted_at": datetime.utcnow().isoformat()
    }
