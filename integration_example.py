"""
Integration Example: Lead Capture → Proposal API → Proposal Generator → PDF
===========================================================================

This example shows how to:
1. Take lead capture form data
2. Generate proposal via this API
3. Convert proposal JSON through normalizer
4. Generate PDF using the proposal generator
"""

import json
import sys
import os
from pathlib import Path

# Add paths for imports
PROPOSAL_PATH = Path(__file__).parent.parent / "Proposal(2)" / "proposal"
sys.path.insert(0, str(PROPOSAL_PATH))
sys.path.insert(0, str(Path(__file__).parent))

from pricing_engine import PricingEngine
from proposal_builder import ProposalBuilder

# Try to import proposal generator components (optional)
try:
    from normalizer import normalize_proposal
    HAS_NORMALIZER = True
except ImportError:
    HAS_NORMALIZER = False
    print("Warning: normalizer.py not found. Skipping normalization step.")

try:
    from generator import generate
    HAS_GENERATOR = True
except ImportError:
    HAS_GENERATOR = False
    print("Warning: generator.py not found. Skipping PDF generation step.")


class ProposalPipeline:
    """End-to-end proposal generation pipeline"""
    
    def __init__(self):
        self.lead_data = None
        self.proposal = None
        self.normalized_proposal = None
        self.pdf_output = None
    
    def load_lead_capture(self, json_file_or_dict):
        """Load lead capture data"""
        if isinstance(json_file_or_dict, str):
            with open(json_file_or_dict) as f:
                self.lead_data = json.load(f)
        else:
            self.lead_data = json_file_or_dict
        
        print("✅ Lead capture data loaded")
        return self
    
    def generate_proposal(self):
        """Generate proposal from lead capture data"""
        if not self.lead_data:
            raise ValueError("No lead capture data loaded")
        
        builder = ProposalBuilder(self.lead_data)
        self.proposal = builder.build_complete_proposal()
        
        print(f"✅ Proposal generated with {len(self.proposal.get('pages', []))} pages")
        return self
    
    def normalize_proposal(self):
        """Normalize proposal for PDF generation"""
        if not self.proposal:
            raise ValueError("No proposal generated yet")
        
        if not HAS_NORMALIZER:
            print("⚠️  Normalizer not available, skipping normalization")
            self.normalized_proposal = self.proposal
            return self
        
        # Wrap proposal in pages structure if needed
        proposal_structure = {
            "pages": self.proposal.get("pages", [])
        }
        
        self.normalized_proposal = normalize_proposal(proposal_structure)
        print("✅ Proposal normalized")
        return self
    
    def generate_pdf(self, output_file="proposal.pdf"):
        """Generate PDF from proposal"""
        if not self.normalized_proposal:
            print("⚠️  Normalized proposal not available, using raw proposal")
            proposal_to_use = self.proposal
        else:
            proposal_to_use = self.normalized_proposal
        
        if not HAS_GENERATOR:
            print("⚠️  Generator not available, saving JSON instead")
            self.save_proposal_json(output_file.replace(".pdf", ".json"))
            return self
        
        try:
            # Convert proposal to generator format
            project_description = json.dumps(proposal_to_use)
            
            # Generate PDF
            generate(project_description, output_file)
            self.pdf_output = output_file
            print(f"✅ PDF generated: {output_file}")
        except Exception as e:
            print(f"⚠️  PDF generation failed: {str(e)}")
            print("   Saving proposal JSON instead")
            self.save_proposal_json(output_file.replace(".pdf", ".json"))
        
        return self
    
    def save_proposal_json(self, output_file="proposal.json"):
        """Save proposal as JSON"""
        proposal = self.normalized_proposal or self.proposal
        
        if not proposal:
            raise ValueError("No proposal to save")
        
        with open(output_file, 'w') as f:
            json.dump(proposal, f, indent=2)
        
        print(f"✅ Proposal saved: {output_file}")
        return self
    
    def save_pricing_summary(self, output_file="pricing_summary.json"):
        """Save just the pricing information"""
        if not self.lead_data:
            raise ValueError("No lead data available")
        
        pricing_engine = PricingEngine()
        pricing = pricing_engine.build_proposal_pricing_table(self.lead_data)
        
        with open(output_file, 'w') as f:
            json.dump(pricing, f, indent=2)
        
        print(f"✅ Pricing summary saved: {output_file}")
        return self
    
    def get_summary(self):
        """Get pipeline execution summary"""
        if not self.proposal:
            return {"status": "Not started"}
        
        pricing_engine = PricingEngine()
        pricing = pricing_engine.build_proposal_pricing_table(self.lead_data)
        
        return {
            "status": "Complete",
            "pages": len(self.proposal.get("pages", [])),
            "title": self.proposal.get("title"),
            "pricing": {
                "subtotal": pricing.get("summary", {}).get("subtotal"),
                "contingency": pricing.get("contingency", {}).get("amount"),
                "total": pricing.get("summary", {}).get("total")
            },
            "files": {
                "proposal_json": "proposal.json",
                "pricing_summary": "pricing_summary.json",
                "pdf": self.pdf_output or "Not generated"
            }
        }


def main():
    """Example pipeline execution"""
    
    print("\n" + "="*70)
    print("PROPOSAL GENERATION PIPELINE")
    print("="*70)
    
    # Get input file
    input_file = Path(__file__).parent / "example_lead_capture.json"
    
    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}")
        return False
    
    try:
        # Create pipeline
        pipeline = ProposalPipeline()
        
        # Step 1: Load lead capture data
        print("\n[Step 1] Loading lead capture data...")
        pipeline.load_lead_capture(str(input_file))
        
        # Step 2: Generate proposal
        print("\n[Step 2] Generating proposal...")
        pipeline.generate_proposal()
        
        # Step 3: Normalize proposal (optional)
        print("\n[Step 3] Normalizing proposal...")
        pipeline.normalize_proposal()
        
        # Step 4: Save outputs
        print("\n[Step 4] Saving outputs...")
        pipeline.save_proposal_json("proposal_output.json")
        pipeline.save_pricing_summary("pricing_summary.json")
        
        # Step 5: Generate PDF (optional)
        print("\n[Step 5] Generating PDF...")
        pipeline.generate_pdf("proposal_output.pdf")
        
        # Print summary
        print("\n" + "="*70)
        print("PIPELINE SUMMARY")
        print("="*70)
        summary = pipeline.get_summary()
        for key, value in summary.items():
            if isinstance(value, dict):
                print(f"{key}:")
                for k, v in value.items():
                    print(f"  {k}: {v}")
            else:
                print(f"{key}: {value}")
        
        print("\n✅ Pipeline completed successfully!")
        return True
    
    except Exception as e:
        print(f"\n❌ Pipeline failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
