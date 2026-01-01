"""
Quick test script for invoice_sample_2.json
"""
import json
import requests
from pathlib import Path

# Load second invoice sample
with open("sample_data/invoice_sample_2.json", 'r') as f:
    invoice = json.load(f)

print("📄 Testing with Invoice 2:")
print(f"   Invoice ID: {invoice['invoice_id']}")
print(f"   Vendor: {invoice['vendor_name']}")
print(f"   Amount: ${invoice['amount']}")
print()

# Execute workflow
print("🚀 Executing workflow...")
response = requests.post(
    "http://localhost:5000/api/workflow/execute",
    json={"invoice_payload": invoice}
)

if response.status_code == 200:
    result = response.json()
    print("✅ Success!")
    print(f"   Workflow ID: {result['workflow_id']}")
    print(f"   Status: {result['status']}")
    print(f"   Current Stage: {result['current_stage']}")
    
    if result.get('requires_human_review'):
        print(f"\n⏸️  HITL Required!")
        print(f"   Checkpoint ID: {result['checkpoint_id']}")
        print(f"   Review URL: http://localhost:5000{result['review_url']}")
    else:
        print("\n✅ Completed without HITL")
else:
    print(f"❌ Failed: {response.json()}")
