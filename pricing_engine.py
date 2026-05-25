"""
Pricing Engine v1 — Lead Capture to Proposal Pricing
=====================================================
Converts lead capture form data into structured pricing tables
with detailed justifications for each line item.
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from decimal import Decimal


class PricingItem:
    """Represents a single pricing line item"""
    def __init__(self, item_name: str, category: str, base_price: float, 
                 quantity: int = 1, justification: str = ""):
        self.item_name = item_name
        self.category = category
        self.base_price = float(base_price)
        self.quantity = quantity
        self.justification = justification
    
    @property
    def subtotal(self) -> float:
        return self.base_price * self.quantity
    
    def to_dict(self) -> Dict:
        return {
            "itemName": self.item_name,
            "category": self.category,
            "basePrice": self.base_price,
            "quantity": self.quantity,
            "subtotal": self.subtotal,
            "justification": self.justification
        }


class PricingEngine:
    """Main pricing calculation engine"""
    
    def __init__(self):
        self.items: List[PricingItem] = []
        self.project_params: Dict[str, Any] = {}
        self.complexity_multiplier = 1.0
        self.service_selections: Dict[str, Any] = {}

    @staticmethod
    def _currency_symbol(currency_code: str) -> str:
        """Map common currency codes to display symbols."""
        code = (currency_code or "USD").upper()
        return {
            "USD": "$",
            "INR": "₹",
            "EUR": "€",
            "GBP": "£",
            "CAD": "C$",
            "AUD": "A$",
            "AED": "AED ",
            "SAR": "SAR ",
            "QAR": "QAR ",
        }.get(code, f"{code} ")

    def format_currency_amount(self, amount: float, currency_code: str = "USD") -> str:
        """Format amounts for the selected currency."""
        symbol = self._currency_symbol(currency_code)
        return f"{symbol}{amount:,.2f}"
    
    def parse_lead_capture(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and parse lead capture form data"""
        lead_fields = lead_data.get("leadCapture", {}).get("fields", [])
        parsed = {}
        
        for field in lead_fields:
            field_name = field.get("fieldName")
            if field_name:
                parsed[field_name] = {
                    "description": field.get("description"),
                    "type": field.get("type"),
                    "required": field.get("required", False)
                }
        
        self.project_params = parsed
        return parsed
    
    def analyze_service_complexity(self, form_data: Dict[str, Any]) -> float:
        """Analyze service complexity to adjust pricing multiplier"""
        complexity_score = 1.0
        
        # Check project timeline - urgency increases complexity
        timeline = form_data.get("projectTimeline", "")
        if "1-3 months" in timeline:
            complexity_score *= 1.15  # Rush premium
        elif "3-6 months" in timeline:
            complexity_score *= 1.05
        
        # Check for location complexity (international = +10%)
        location = form_data.get("projectLocation", "").lower()
        if any(word in location for word in ["international", "abroad", "overseas"]):
            complexity_score *= 1.10
        
        return complexity_score
    
    def build_pricing_from_services(self, data: Dict[str, Any]) -> List[PricingItem]:
        """Build pricing items from service types data"""
        self.items = []
        service_types = data.get("serviceTypes", {}).get("fields", [])
        
        for service in service_types:
            service_name = service.get("serviceName", "Unknown Service")
            if not service.get("isActive"):
                continue
            
            # Create service category header
            service_fields = service.get("fields", [])
            service_total_price = 0.0
            service_justifications = []
            
            for field in service_fields:
                field_name = field.get("fieldName", "")
                description = field.get("description", "")
                field_type = field.get("type", "")
                options = field.get("options", [])
                price_matrix_enabled = field.get("priceMatrixEnabled", False)
                
                # For demonstration, we'll use the first option or calculate average
                if options:
                    if field_type == "multiselect":
                        # Sum all options for multiselect
                        total = sum(opt.get("price", 0) for opt in options)
                        item = PricingItem(
                            item_name=f"{description} (Multi-service)",
                            category=service_name,
                            base_price=total,
                            quantity=1,
                            justification=f"Multi-select service options for {field_name}"
                        )
                    else:
                        # Use first option or average
                        avg_price = sum(opt.get("price", 0) for opt in options) / len(options)
                        item = PricingItem(
                            item_name=description,
                            category=service_name,
                            base_price=avg_price,
                            quantity=1,
                            justification=f"Standard {field_name} pricing based on service tier"
                        )
                    
                    self.items.append(item)
                    service_total_price += item.base_price
                    service_justifications.append(item.justification)
        
        return self.items
    
    def add_item(self, item_name: str, category: str, base_price: float, 
                 quantity: int = 1, justification: str = "") -> PricingItem:
        """Manually add a pricing item"""
        item = PricingItem(item_name, category, base_price, quantity, justification)
        self.items.append(item)
        return item
    
    def calculate_subtotal(self) -> float:
        """Calculate subtotal before adjustments"""
        return sum(item.subtotal for item in self.items)
    
    def calculate_contingency(self, percentage: float = 10) -> float:
        """Calculate contingency percentage (typical 10-15%)"""
        subtotal = self.calculate_subtotal()
        return subtotal * (percentage / 100)
    
    def calculate_grand_total(self, contingency_pct: float = 10, tax_pct: float = 0) -> float:
        """Calculate grand total with contingency and tax"""
        subtotal = self.calculate_subtotal()
        contingency = self.calculate_contingency(contingency_pct)
        tax = (subtotal + contingency) * (tax_pct / 100)
        return subtotal + contingency + tax
    
    def generate_justifications(self, form_data: Dict[str, Any]) -> Dict[str, str]:
        """Generate detailed justifications for pricing"""
        justifications = {}
        
        # Basic service justifications
        justifications["service_selection"] = (
            "Pricing is based on selected service categories and complexity levels. "
            "Each service tier includes professional expertise, project management, "
            "and quality assurance."
        )
        
        # Project timeline impact
        timeline = form_data.get("projectTimeline", "")
        if "1-3 months" in timeline:
            justifications["timeline_premium"] = (
                f"Rush Timeline Premium (15%): Project execution within 1-3 months "
                f"requires expedited scheduling, resource allocation, and potential overtime."
            )
        elif "3-6 months" in timeline:
            justifications["timeline_premium"] = (
                f"Accelerated Timeline Premium (5%): 3-6 month timeline requires "
                f"optimized project phases and coordinated team resources."
            )
        else:
            justifications["timeline_premium"] = (
                f"Standard Timeline: 6+ month timeline allows efficient phasing "
                f"and resource optimization."
            )
        
        # Location complexity
        location = form_data.get("projectLocation", "")
        justifications["location_impact"] = (
            f"Location-based Adjustments: Project location ({location}) impacts travel, "
            f"logistics, and local compliance requirements."
        )
        
        # Contingency
        justifications["contingency"] = (
            "10% Contingency Reserve: Industry-standard allocation for unforeseen "
            "project changes, site conditions, or scope clarifications."
        )
        
        return justifications
    
    def get_pricing_breakdown(self, currency_code: str = "USD") -> Dict[str, Any]:
        """Get complete pricing breakdown"""
        subtotal = self.calculate_subtotal()
        contingency = self.calculate_contingency(10)
        grand_total = self.calculate_grand_total(10, 0)
        
        return {
            "items": [item.to_dict() for item in self.items],
            "subtotal": subtotal,
            "contingency": {
                "percentage": 10,
                "amount": contingency,
                "justification": "Industry-standard contingency for project variables"
            },
            "total": grand_total,
            "currency": currency_code,
            "generatedAt": datetime.now().isoformat()
        }
    
    def build_proposal_pricing_table(self, form_data: Dict[str, Any], currency_code: str = "USD") -> Dict[str, Any]:
        """Build final proposal pricing table structure"""
        currency_code = (currency_code or form_data.get("meta", {}).get("currency") or "USD").upper()

        # Analyze complexity
        self.complexity_multiplier = self.analyze_service_complexity(form_data)
        
        # Build items from services
        self.build_pricing_from_services(form_data)
        
        # Generate justifications
        justifications = self.generate_justifications(form_data)
        
        # Build table structure
        table_content = []
        categories_seen = set()
        
        for item in self.items:
            if item.category not in categories_seen:
                # Add category header
                categories_seen.add(item.category)
                header_row = [
                    {"value": f"{item.category} Services", "label": f"{item.category}", "isHeader": True},
                    {"value": "", "label": "", "isHeader": True},
                    {"value": "", "label": "", "isHeader": True}
                ]
                table_content.append(header_row)
            
            # Add item row
            item_row = [
                {"value": item.item_name},
                {"value": self.format_currency_amount(item.base_price, currency_code)},
                {"value": str(item.quantity)}
            ]
            table_content.append(item_row)
        
        # Add subtotal row
        subtotal = self.calculate_subtotal()
        subtotal_row = [
            {"value": "Subtotal", "bold": True},
            {"value": self.format_currency_amount(subtotal, currency_code), "bold": True},
            {"value": ""}
        ]
        table_content.append(subtotal_row)
        
        # Add contingency row
        contingency = self.calculate_contingency(10)
        contingency_row = [
            {"value": "Contingency (10%)"},
            {"value": self.format_currency_amount(contingency, currency_code)},
            {"value": ""}
        ]
        table_content.append(contingency_row)
        
        # Add total row
        grand_total = self.calculate_grand_total(10, 0)
        total_row = [
            {"value": "Total Project Cost", "bold": True},
            {"value": self.format_currency_amount(grand_total, currency_code), "bold": True},
            {"value": ""}
        ]
        table_content.append(total_row)
        
        return {
            "header": [
                {"value": "Service / Item", "label": "Service"},
                {"value": "Price", "label": "Price"},
                {"value": "Qty", "label": "Quantity"}
            ],
            "content": table_content,
            "summary": {
                "subtotal": subtotal,
                "contingency": contingency,
                "total": grand_total,
                "currency": currency_code
            },
            "justifications": justifications
        }


def extract_form_values(form_submission: Dict[str, Any]) -> Dict[str, Any]:
    """Extract actual form values from submission"""
    # This would be called when a user submits the form with actual selections
    extracted = {}
    
    # Parse lead capture values
    lead_capture = form_submission.get("leadCapture", {})
    for field_name, value in lead_capture.items():
        extracted[field_name] = value
    
    # Parse service selections
    services = form_submission.get("serviceTypes", {})
    for service_name, selections in services.items():
        extracted[service_name] = selections
    
    return extracted
