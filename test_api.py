#!/usr/bin/env python3
"""
Quick Start Script for Lead Capture to Proposal API
=====================================================
Tests the single proposal endpoint with example data.
"""

import json
import requests
import sys
from pathlib import Path


def load_example_data():
    """Load example lead capture data"""
    example_file = Path(__file__).parent / "example_lead_capture.json"
    with open(example_file) as f:
        return json.load(f)


def test_generate_proposal(base_url, data):
    """Test: Generate full proposal endpoint"""
    print("\n" + "=" * 60)
    print("TEST: Generate Proposal")
    print("=" * 60)

    response = requests.post(
        f"{base_url}/api/v1/generate-proposal",
        json=data
    )
    print(f"Status: {response.status_code}")

    result = response.json()
    if response.status_code == 200:
        print(f"Success: {result.get('success')}")
        print(f"Message: {result.get('message')}")

        proposal = result.get('proposal', {})
        print(f"Proposal Title: {proposal.get('title')}")
        print(f"Number of Pages: {len(proposal.get('pages', []))}")

        print("Pages:")
        for page in proposal.get('pages', []):
            print(f"  - {page.get('name')} ({page.get('type')})")

        pricing = result.get('pricingTable', {})
        summary = pricing.get('summary', {})
        print("\nPricing Summary:")
        print(f"  - Subtotal: ${summary.get('subtotal', 0):,.2f}")
        print(f"  - Contingency: ${summary.get('contingency', 0):,.2f}")
        print(f"  - Total: ${summary.get('total', 0):,.2f}")

        justification_text = result.get('justificationText', [])
        print("\nJustification Text Blocks:")
        for item in justification_text:
            print(f"  - {item.get('key')}: {item.get('text')[:100]}...")

        output_file = Path(__file__).parent / "proposal_output.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\nProposal saved to: {output_file}")

    return response.status_code == 200


def run_test(base_url="http://localhost:8000"):
    """Run the single endpoint test"""
    print("\n" + "█" * 60)
    print("█ Lead Capture to Proposal API - Test")
    print("█" * 60)

    try:
        requests.get(f"{base_url}/docs", timeout=2)
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Cannot connect to API at {base_url}")
        print("\nMake sure to start the API server first:")
        print("  python api.py")
        return False

    print(f"\n✅ Connected to API at {base_url}")

    data = load_example_data()
    print("✅ Loaded example lead capture data")

    try:
        result = test_generate_proposal(base_url, data)
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        result = False

    print("\n" + "█" * 60)
    print("█ Test Summary")
    print("█" * 60)
    print(f"{'✅ PASS' if result else '❌ FAIL'}: Generate Proposal")

    if result:
        print("\n🎉 Endpoint is working correctly.")
        return True

    print("\n⚠️  Check the output above.")
    return False


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    success = run_test(base_url)
    sys.exit(0 if success else 1)
