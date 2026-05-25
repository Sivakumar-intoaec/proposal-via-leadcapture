"""
Proposal Builder v1 — Convert Pricing to Proposal Pages
=========================================================
Takes pricing calculations and builds complete proposal pages
with AI-designed layouts and pricing tables.
"""

import json
import sys
import os
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pricing_engine import PricingEngine


class ProposalBuilder:
    """Builds proposal structure with pricing tables and justifications"""
    
    def __init__(self, form_data: Dict[str, Any], ai_content: Optional[Dict[str, Any]] = None):
        self.form_data = form_data
        self.pricing_engine = PricingEngine()
        self.ai_content = ai_content or {}
        self.proposal = {
            "title": "",
            "subtitle": "",
            "pages": [],
            "metadata": {
                "generatedAt": datetime.now().isoformat(),
                "version": "1.0",
                "currency": "USD"
            }
        }
    
    def extract_lead_info(self) -> Dict[str, str]:
        """Extract lead information from form data"""
        lead_capture = self.form_data.get("leadCapture", {}).get("fields", [])
        lead_info = {}
        
        # Create a map of fieldName to value
        # In real implementation, form would have actual submitted values
        for field in lead_capture:
            field_name = field.get("fieldName")
            description = field.get("description")
            field_type = field.get("type")
            
            # For now, use placeholder values - in real API, these come from form submission
            if field_name == "fullName":
                lead_info["name"] = "{LEAD_NAME}"
            elif field_name == "email":
                lead_info["email"] = "{LEAD_EMAIL}"
            elif field_name == "phone":
                lead_info["phone"] = "{LEAD_PHONE_NUMBER}"
            elif field_name == "projectLocation":
                lead_info["location"] = "{LEAD_PROJECT_LOCATION}"
            elif field_name == "projectTimeline":
                lead_info["timeline"] = "TBD"
        
        return lead_info

    def _ai_text(self, key: str, fallback: str) -> str:
        """Return AI-generated text when available, otherwise fallback."""
        value = self.ai_content.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return fallback

    def _ai_paragraphs(self, key: str, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return AI-generated paragraph blocks when available."""
        value = self.ai_content.get(key)
        if isinstance(value, list) and value:
            paragraphs = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    paragraphs.append({
                        "type": "p",
                        "children": [{"text": item.strip(), "fontSize": 13, "color": "#333333"}],
                        "lineHeight": 1.8
                    })
            if paragraphs:
                return paragraphs
        return fallback
    
    def get_project_title(self) -> str:
        """Generate project title from service types"""
        ai_title = self.ai_content.get("title")
        if isinstance(ai_title, str) and ai_title.strip():
            return ai_title.strip()

        service_types = self.form_data.get("serviceTypes", {}).get("fields", [])
        active_services = [s.get("serviceName") for s in service_types if s.get("isActive")]
        
        if active_services:
            if len(active_services) == 1:
                return f"{active_services[0]} Project Proposal"
            else:
                return f"Integrated {' & '.join(active_services)} Services Proposal"
        return "Professional Services Proposal"
    
    def build_cover_page(self) -> Dict[str, Any]:
        """Build cover/title page"""
        lead_info = self.extract_lead_info()
        project_title = self.get_project_title()
        
        page = {
            "name": "Cover",
            "type": "cover",
            "layout": "hero_bold_type",
            "objective": "Project Introduction",
            "controllers": [
                {
                    "controllerName": "SHAPE",
                    "x": 0,
                    "y": 0,
                    "width": 792,
                    "height": 1120,
                    "style": {
                        "width": 792,
                        "height": 1120,
                        "backgroundColor": "rgba(15, 23, 42, 1)",
                        "borderRadius": 0
                    },
                    "value": {"shape": "square"}
                },
                {
                    "controllerName": "ORGANIZATION_LOGO",
                    "x": 48,
                    "y": 32,
                    "style": {"width": "100px", "height": "40px"}
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 400,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "h1",
                            "children": [{"text": project_title, "fontSize": 48, "color": "#FFFFFF", "bold": True}],
                            "lineHeight": 1.2
                        }
                    ]
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 550,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "p",
                            "children": [{"text": f"Prepared for: {lead_info.get('name', 'Valued Client')}", "fontSize": 16, "color": "#E0E7FF"}],
                            "lineHeight": 1.6
                        }
                    ]
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 620,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "p",
                            "children": [{"text": f"Location: {lead_info.get('location', 'Project Site')}", "fontSize": 14, "color": "#C7D2FE"}],
                            "lineHeight": 1.6
                        }
                    ]
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 900,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "p",
                            "children": [{"text": f"Date: {datetime.now().strftime('%B %d, %Y')}", "fontSize": 12, "color": "#9CA3AF"}],
                            "lineHeight": 1.6
                        }
                    ]
                }
            ]
        }
        
        return page
    
    def build_pricing_page(self) -> Dict[str, Any]:
        """Build pricing/investment page with table and justifications"""
        # Generate pricing table
        currency_code = self.form_data.get("meta", {}).get("currency", "USD")
        pricing_table = self.pricing_engine.build_proposal_pricing_table(self.form_data, currency_code)
        pricing_intro = self._ai_text(
            "pricing_intro",
            "Transparent cost breakdown with professional service tiers and contingency planning."
        )
        
        page = {
            "name": "Investment Breakdown",
            "type": "investment",
            "layout": "invest_split_panel",
            "objective": "Detailed Pricing & Investment",
            "controllers": [
                {
                    "controllerName": "SHAPE",
                    "x": 0,
                    "y": 0,
                    "width": 792,
                    "height": 1120,
                    "style": {
                        "width": 792,
                        "height": 1120,
                        "backgroundColor": "rgba(255, 255, 255, 1)",
                        "borderRadius": 0
                    },
                    "value": {"shape": "square"}
                },
                {
                    "controllerName": "ORGANIZATION_LOGO",
                    "x": 48,
                    "y": 32,
                    "style": {"width": "80px", "height": "32px"}
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 80,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "h2",
                            "children": [{"text": "Investment Breakdown", "fontSize": 32, "color": "#0F172A", "bold": True}],
                            "lineHeight": 1.2
                        }
                    ]
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 140,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "p",
                            "children": [{"text": pricing_intro, "fontSize": 13, "color": "#666666"}],
                            "lineHeight": 1.6
                        }
                    ]
                },
                {
                    "controllerName": "PRICING_TABLE",
                    "x": 48,
                    "y": 220,
                    "style": {"width": 728, "height": "auto"},
                    "header": pricing_table.get("header", []),
                    "content": pricing_table.get("content", []),
                    "value": pricing_table.get("summary", {})
                }
            ]
        }
        
        return page
    
    def build_justification_page(self) -> Dict[str, Any]:
        """Build page explaining pricing justifications"""
        currency_code = self.form_data.get("meta", {}).get("currency", "USD")
        pricing_table = self.pricing_engine.build_proposal_pricing_table(self.form_data, currency_code)
        justifications = pricing_table.get("justifications", {})
        justification_sections = self.ai_content.get("justification_sections")
        if isinstance(justification_sections, list) and justification_sections:
            justification_text = self._ai_paragraphs("justification_sections", self._build_justification_narrative(justifications))
        else:
            justification_text = self._build_justification_narrative(justifications)
        
        page = {
            "name": "Pricing Justification",
            "type": "content",
            "layout": "scope_dark_cards",
            "objective": "Pricing Rationale & Value Proposition",
            "controllers": [
                {
                    "controllerName": "SHAPE",
                    "x": 0,
                    "y": 0,
                    "width": 792,
                    "height": 1120,
                    "style": {
                        "width": 792,
                        "height": 1120,
                        "backgroundColor": "rgba(255, 255, 255, 1)",
                        "borderRadius": 0
                    },
                    "value": {"shape": "square"}
                },
                {
                    "controllerName": "ORGANIZATION_LOGO",
                    "x": 48,
                    "y": 32,
                    "style": {"width": "80px", "height": "32px"}
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 80,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "h2",
                            "children": [{"text": self._ai_text("justification_title", "Pricing Justification"), "fontSize": 32, "color": "#0F172A", "bold": True}],
                            "lineHeight": 1.2
                        }
                    ]
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 150,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": justification_text
                }
            ]
        }
        
        return page
    
    def _build_justification_narrative(self, justifications: Dict[str, str]) -> List[Dict[str, Any]]:
        """Convert justifications into narrative text blocks"""
        narrative = []
        
        for key, value in justifications.items():
            narrative.append({
                "type": "p",
                "children": [{"text": value, "fontSize": 13, "color": "#333333"}],
                "lineHeight": 1.8
            })
        
        return narrative
    
    def build_acceptance_page(self) -> Dict[str, Any]:
        """Build acceptance/signature page"""
        acceptance_intro = self._ai_text(
            "acceptance_intro",
            "To proceed with this project, please sign below to confirm your agreement with the proposed scope, timeline, and investment."
        )
        page = {
            "name": "Acceptance & Next Steps",
            "type": "acceptance",
            "layout": "accept_full_dark",
            "objective": "Project Agreement & Sign-off",
            "controllers": [
                {
                    "controllerName": "SHAPE",
                    "x": 0,
                    "y": 0,
                    "width": 792,
                    "height": 1120,
                    "style": {
                        "width": 792,
                        "height": 1120,
                        "backgroundColor": "rgba(15, 23, 42, 1)",
                        "borderRadius": 0
                    },
                    "value": {"shape": "square"}
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 200,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "h2",
                            "children": [{"text": "Acceptance & Next Steps", "fontSize": 28, "color": "#FFFFFF", "bold": True}],
                            "lineHeight": 1.2
                        }
                    ]
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 280,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "p",
                            "children": [{"text": acceptance_intro, "fontSize": 13, "color": "#E0E7FF"}],
                            "lineHeight": 1.8
                        }
                    ]
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 380,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "h3",
                            "children": [{"text": "Client Signature", "fontSize": 14, "color": "#FFFFFF", "bold": True}],
                            "lineHeight": 1.2
                        }
                    ]
                },
                {
                    "controllerName": "SIGNATURE",
                    "x": 48,
                    "y": 428,
                    "signatureType": "CLIENT"
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 520,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "h3",
                            "children": [{"text": "Administrator Signature", "fontSize": 14, "color": "#FFFFFF", "bold": True}],
                            "lineHeight": 1.2
                        }
                    ]
                },
                {
                    "controllerName": "SIGNATURE",
                    "x": 48,
                    "y": 568,
                    "signatureType": "ADMIN"
                },
                {
                    "controllerName": "TEXT",
                    "x": 48,
                    "y": 700,
                    "width": "696px",
                    "style": {"width": "696px", "height": "auto"},
                    "value": [
                        {
                            "type": "p",
                            "children": [{"text": f"Date: {datetime.now().strftime('%B %d, %Y')}", "fontSize": 12, "color": "#9CA3AF"}],
                            "lineHeight": 1.6
                        }
                    ]
                }
            ]
        }
        
        return page
    
    def build_complete_proposal(self) -> Dict[str, Any]:
        """Build complete proposal with all pages"""
        self.proposal["title"] = self.get_project_title()
        self.proposal["subtitle"] = self._ai_text(
            "subtitle",
            "Professional Design & Development Services"
        )
        
        # Add pages in order
        self.proposal["pages"] = [
            self.build_cover_page(),
            self.build_pricing_page(),
            self.build_justification_page(),
            self.build_acceptance_page()
        ]
        
        return self.proposal
    
    def to_json(self) -> str:
        """Export proposal as JSON string"""
        return json.dumps(self.proposal, indent=2)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export proposal as dictionary"""
        return self.proposal


def create_proposal_from_lead_capture(lead_capture_json: Dict[str, Any]) -> Dict[str, Any]:
    """Main entry point: Convert lead capture form to proposal"""
    
    # Validate input
    if "leadCapture" not in lead_capture_json or "serviceTypes" not in lead_capture_json:
        raise ValueError("Invalid lead capture JSON structure")
    
    # Build proposal
    builder = ProposalBuilder(lead_capture_json)
    proposal = builder.build_complete_proposal()
    
    return proposal
