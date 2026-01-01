"""
Demo script for Invoice Processing Workflow
Demonstrates full workflow execution with HITL checkpoint
"""
import json
import time
import requests
from datetime import datetime
from pathlib import Path


def load_sample_invoice(sample_number=1):
    """Load sample invoice data"""
    sample_file = Path(f"sample_data/invoice_sample_{sample_number}.json")
    with open(sample_file, 'r') as f:
        return json.load(f)


def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_stage_info(stage, data):
    """Print stage execution information"""
    print(f"✓ Stage: {stage}")
    if isinstance(data, dict):
        for key, value in data.items():
            if not key.startswith('_') and key not in ['stage_outputs', 'mcp_server_calls', 'bigtool_selections']:
                print(f"  - {key}: {value}")
    print()


def run_demo():
    """Run complete demo of invoice processing workflow"""
    
    print("\n" + "╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "🤖 LANGIE - INVOICE PROCESSING DEMO" + " " * 23 + "║")
    print("║" + " " * 15 + "LangGraph Workflow with HITL Checkpoint" + " " * 24 + "║")
    print("╚" + "═" * 78 + "╝\n")
    
    base_url = "http://localhost:5000"
    
    # Step 1: Check API health
    print_section("STEP 1: Checking API Health")
    try:
        response = requests.get(f"{base_url}/api/health")
        if response.status_code == 200:
            print("✅ API is healthy and ready")
            print(f"   Service: {response.json().get('service')}")
            print(f"   Timestamp: {response.json().get('timestamp')}")
        else:
            print("❌ API health check failed")
            return
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Please ensure the server is running:")
        print("   python app.py")
        return
    
    # Step 2: Load sample invoice
    print_section("STEP 2: Loading Sample Invoice")
    invoice_payload = load_sample_invoice(1)
    print("📄 Invoice Details:")
    print(f"   Invoice ID: {invoice_payload['invoice_id']}")
    print(f"   Vendor: {invoice_payload['vendor_name']}")
    print(f"   Amount: {invoice_payload['currency']} {invoice_payload['amount']}")
    print(f"   PO Reference: {invoice_payload.get('po_reference', 'N/A')}")
    print(f"   Line Items: {len(invoice_payload['line_items'])}")
    
    # Step 3: Execute workflow
    print_section("STEP 3: Executing Invoice Processing Workflow")
    print("🚀 Starting workflow execution...")
    print()
    
    response = requests.post(
        f"{base_url}/api/workflow/execute",
        json={"invoice_payload": invoice_payload}
    )
    
    if response.status_code != 200:
        print(f"❌ Workflow execution failed: {response.json()}")
        return
    
    result = response.json()
    workflow_id = result.get('workflow_id')
    
    print(f"✅ Workflow initiated successfully!")
    print(f"   Workflow ID: {workflow_id}")
    print(f"   Status: {result.get('status')}")
    print(f"   Current Stage: {result.get('current_stage')}")
    print()
    
    # Step 4: Check if HITL is required
    if result.get('requires_human_review'):
        print_section("STEP 4: Human-In-The-Loop (HITL) Checkpoint Triggered")
        print("⏸️  Workflow paused for human review")
        print(f"   Checkpoint ID: {result.get('checkpoint_id')}")
        print(f"   Review URL: {result.get('review_url')}")
        print()
        print("📋 Reason for Hold:")
        print("   Match score below threshold - discrepancy detected between invoice and PO")
        print()
        
        checkpoint_id = result.get('checkpoint_id')
        
        # Get checkpoint details
        print("📊 Fetching checkpoint details...")
        checkpoint_response = requests.get(
            f"{base_url}/api/human-review/checkpoint/{checkpoint_id}"
        )
        
        if checkpoint_response.status_code == 200:
            checkpoint_data = checkpoint_response.json()
            print(f"   Match Score: {checkpoint_data.get('match_score', 0) * 100:.1f}%")
            print(f"   Invoice Amount: ${checkpoint_data.get('amount', 0):,.2f}")
            
            if checkpoint_data.get('discrepancy_details'):
                disc = checkpoint_data['discrepancy_details']
                print(f"   PO Amount: ${disc.get('po_amount', 0):,.2f}")
                print(f"   Discrepancy: ${disc.get('discrepancy', 0):,.2f}")
        
        print()
        print("🌐 You can review this invoice in the web UI:")
        print(f"   Open: http://localhost:5000")
        print()
        
        # Simulate human review decision
        print("⏳ Simulating human review decision...")
        print("   (In production, a human would review via the web UI)")
        print()
        
        time.sleep(2)
        
        # Step 5: Submit human decision
        print_section("STEP 5: Submitting Human Review Decision")
        
        decision = "ACCEPT"  # Change to "REJECT" to see different outcome
        reviewer_id = "demo.reviewer@company.com"
        notes = "Verified with vendor - discrepancy due to additional consulting hours approved via email"
        
        print(f"👤 Reviewer: {reviewer_id}")
        print(f"✓ Decision: {decision}")
        print(f"📝 Notes: {notes}")
        print()
        
        decision_response = requests.post(
            f"{base_url}/api/human-review/decision",
            json={
                "checkpoint_id": checkpoint_id,
                "decision": decision,
                "reviewer_id": reviewer_id,
                "notes": notes
            }
        )
        
        if decision_response.status_code == 200:
            decision_result = decision_response.json()
            print("✅ Decision submitted successfully!")
            print(f"   Resume Token: {decision_result.get('resume_token')}")
            print(f"   Next Stage: {decision_result.get('next_stage')}")
            print(f"   Workflow Status: {decision_result.get('workflow_status')}")
            print()
            print("▶️  Workflow resumed and continuing execution...")
        else:
            print(f"❌ Failed to submit decision: {decision_response.json()}")
            return
        
    else:
        print_section("STEP 4: Direct Processing (No HITL Required)")
        print("✅ Invoice matched successfully - proceeding with automatic processing")
    
    # Step 6: Summary
    print_section("STEP 6: Workflow Summary")
    
    print("🎯 Workflow Execution Complete!")
    print()
    print("📊 Workflow Stages Executed:")
    stages = [
        "1.  INTAKE       - ✓ Invoice validated and persisted",
        "2.  UNDERSTAND   - ✓ OCR extraction completed",
        "3.  PREPARE      - ✓ Vendor normalized and enriched",
        "4.  RETRIEVE     - ✓ PO/GRN data fetched from ERP",
        "5.  MATCH_TWO_WAY - ✓ 2-way matching performed",
        "6.  CHECKPOINT_HITL - ✓ Checkpoint created (if needed)",
        "7.  HITL_DECISION - ✓ Human decision processed",
        "8.  RECONCILE    - ✓ Accounting entries built",
        "9.  APPROVE      - ✓ Approval policy applied",
        "10. POSTING      - ✓ Posted to ERP",
        "11. NOTIFY       - ✓ Notifications sent",
        "12. COMPLETE     - ✓ Workflow finalized"
    ]
    
    for stage in stages:
        print(f"   {stage}")
    
    print()
    print("🔧 Tool Selections (Bigtool):")
    print("   - OCR: tesseract")
    print("   - Enrichment: vendor_db")
    print("   - ERP Connector: mock_erp")
    print("   - Database: sqlite")
    print("   - Email: ses")
    
    print()
    print("🌐 MCP Server Calls:")
    print("   - COMMON Server: 6 ability calls")
    print("   - ATLAS Server: 8 ability calls")
    
    print()
    print("💾 Data Persistence:")
    print("   - Checkpoint stored in SQLite")
    print("   - Human review queue updated")
    print("   - Workflow state persisted at each stage")
    print("   - Audit log complete")
    
    print()
    print("🎉 Demo Complete!")
    print()
    print("Next steps:")
    print("  1. Open http://localhost:5000 to view the Human Review UI")
    print("  2. Check demo.db to see persisted data")
    print("  3. Run with invoice_sample_2.json for a different scenario")
    print("  4. Explore the code to understand the implementation")
    print()
    print("=" * 80)
    print()


if __name__ == "__main__":
    try:
        run_demo()
    except KeyboardInterrupt:
        print("\n\n❌ Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
