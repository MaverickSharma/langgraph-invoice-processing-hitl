"""
Bigtool - Dynamic tool selection system
Selects the most appropriate tool from a pool based on context and requirements
"""
from typing import Dict, List, Optional, Any
import yaml
import os
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


class SelectionMethod(str, Enum):
    """Tool selection method"""
    RULE_BASED = "rule_based"
    LLM_BASED = "llm_based"
    HYBRID = "hybrid"


@dataclass
class ToolProvider:
    """Tool provider configuration"""
    name: str
    priority: int
    cost: str
    latency: str
    accuracy: Optional[str] = None
    conditions: Optional[List[str]] = None
    data_quality: Optional[str] = None
    reliability: Optional[str] = None
    scalability: Optional[str] = None


@dataclass
class ToolSelection:
    """Result of tool selection"""
    capability: str
    selected_tool: str
    selection_method: str
    reason: str
    alternatives: List[str]
    context: Dict[str, Any]


class BigtoolPicker:
    """
    Dynamic tool selector that chooses the best tool from a pool
    based on context, conditions, and selection strategy
    """
    
    def __init__(self, config_path: str = "config/tools.yaml"):
        """Initialize Bigtool with configuration"""
        self.config_path = config_path
        self.config = self._load_config()
        self.tool_pools = self.config.get("tool_pools", {})
        self.selection_strategy = self.config.get("selection_strategy", {})
        self.fallback_config = self.config.get("fallback", {})
        
        logger.info("bigtool_initialized", config_path=config_path)
    
    def _load_config(self) -> Dict:
        """Load tool configuration from YAML"""
        if not os.path.exists(self.config_path):
            logger.warning("config_not_found", path=self.config_path)
            return self._get_default_config()
        
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _get_default_config(self) -> Dict:
        """Get default configuration if file not found"""
        return {
            "tool_pools": {
                "ocr": {
                    "providers": [
                        {"name": "tesseract", "priority": 1, "cost": "low", "latency": "fast"}
                    ]
                },
                "enrichment": {
                    "providers": [
                        {"name": "vendor_db", "priority": 1, "cost": "free", "latency": "fast"}
                    ]
                },
                "erp_connector": {
                    "providers": [
                        {"name": "mock_erp", "priority": 1, "cost": "free", "latency": "fast"}
                    ]
                },
                "db": {
                    "providers": [
                        {"name": "sqlite", "priority": 1, "cost": "free", "latency": "fast"}
                    ]
                },
                "email": {
                    "providers": [
                        {"name": "ses", "priority": 1, "cost": "low", "latency": "medium"}
                    ]
                }
            },
            "selection_strategy": {
                "default_method": "rule_based",
                "rule_based": {"enabled": True}
            },
            "fallback": {"enabled": True}
        }
    
    def select(
        self, 
        capability: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> ToolSelection:
        """
        Select the best tool for the given capability and context
        
        Args:
            capability: The capability needed (ocr, enrichment, erp_connector, db, email)
            context: Context information for selection (environment, requirements, etc.)
        
        Returns:
            ToolSelection with selected tool and reasoning
        """
        if context is None:
            context = {}
        
        # Add default context values
        context.setdefault("environment", os.getenv("ENVIRONMENT", "development"))
        
        logger.info("tool_selection_requested", capability=capability, context=context)
        
        # Get tool pool for capability
        tool_pool = self.tool_pools.get(capability)
        if not tool_pool:
            logger.error("capability_not_found", capability=capability)
            raise ValueError(f"Unknown capability: {capability}")
        
        providers = tool_pool.get("providers", [])
        if not providers:
            logger.error("no_providers_found", capability=capability)
            raise ValueError(f"No providers configured for capability: {capability}")
        
        # Determine selection method
        method = self.selection_strategy.get("default_method", "rule_based")
        
        # Select tool based on method
        if method == SelectionMethod.RULE_BASED:
            selection = self._rule_based_selection(capability, providers, context)
        elif method == SelectionMethod.LLM_BASED:
            selection = self._llm_based_selection(capability, providers, context)
        elif method == SelectionMethod.HYBRID:
            selection = self._hybrid_selection(capability, providers, context)
        else:
            selection = self._rule_based_selection(capability, providers, context)
        
        logger.info(
            "tool_selected",
            capability=capability,
            selected=selection.selected_tool,
            method=selection.selection_method
        )
        
        return selection
    
    def _rule_based_selection(
        self, 
        capability: str, 
        providers: List[Dict],
        context: Dict[str, Any]
    ) -> ToolSelection:
        """
        Rule-based selection using conditions and priorities
        """
        eligible_providers = []
        
        for provider in providers:
            # Check if conditions are met
            conditions = provider.get("conditions", [])
            if self._check_conditions(conditions, context):
                eligible_providers.append(provider)
        
        # If no eligible providers, fallback to highest priority
        if not eligible_providers:
            logger.warning(
                "no_eligible_providers",
                capability=capability,
                using_fallback=True
            )
            eligible_providers = providers
        
        # Sort by priority (lower number = higher priority)
        eligible_providers.sort(key=lambda x: x.get("priority", 999))
        
        # Select first (highest priority) provider
        selected = eligible_providers[0]
        alternatives = [p["name"] for p in eligible_providers[1:]]
        
        reason = f"Selected based on priority={selected.get('priority')} and context match"
        
        return ToolSelection(
            capability=capability,
            selected_tool=selected["name"],
            selection_method="rule_based",
            reason=reason,
            alternatives=alternatives,
            context=context
        )
    
    def _check_conditions(self, conditions: List[str], context: Dict[str, Any]) -> bool:
        """
        Check if all conditions are met given the context
        Simple string-based condition checking
        """
        if not conditions:
            return True
        
        for condition in conditions:
            try:
                # Simple condition evaluation
                # Example: "context.environment == 'development'"
                # For production, use a proper expression evaluator
                
                # Handle simple equality checks
                if " == " in condition:
                    parts = condition.split(" == ")
                    if len(parts) == 2:
                        key = parts[0].strip().replace("context.", "")
                        expected_value = parts[1].strip().strip("'\"")
                        
                        actual_value = context.get(key)
                        if str(actual_value) != expected_value:
                            return False
                
                # Handle 'in' checks
                elif " in " in condition:
                    parts = condition.split(" in ")
                    if len(parts) == 2:
                        key = parts[0].strip().replace("context.", "")
                        values_str = parts[1].strip().strip("[]")
                        expected_values = [v.strip().strip("'\"") for v in values_str.split(",")]
                        
                        actual_value = str(context.get(key, ""))
                        if actual_value not in expected_values:
                            return False
                
                # Handle comparison operators
                elif " < " in condition or " > " in condition or " >= " in condition:
                    # For numeric comparisons
                    for op in [" >= ", " > ", " < ", " <= "]:
                        if op in condition:
                            parts = condition.split(op)
                            if len(parts) == 2:
                                key = parts[0].strip().replace("context.", "")
                                threshold = float(parts[1].strip())
                                actual_value = context.get(key, 0)
                                
                                if op == " >= " and not (actual_value >= threshold):
                                    return False
                                elif op == " > " and not (actual_value > threshold):
                                    return False
                                elif op == " < " and not (actual_value < threshold):
                                    return False
                                elif op == " <= " and not (actual_value <= threshold):
                                    return False
                            break
                
            except Exception as e:
                logger.warning("condition_check_failed", condition=condition, error=str(e))
                continue
        
        return True
    
    def _llm_based_selection(
        self, 
        capability: str, 
        providers: List[Dict],
        context: Dict[str, Any]
    ) -> ToolSelection:
        """
        LLM-based selection using AI reasoning
        Note: Requires OpenAI API key in production
        """
        # For demo, fall back to rule-based
        logger.info("llm_based_selection_requested", note="Using rule-based fallback for demo")
        return self._rule_based_selection(capability, providers, context)
    
    def _hybrid_selection(
        self, 
        capability: str, 
        providers: List[Dict],
        context: Dict[str, Any]
    ) -> ToolSelection:
        """
        Hybrid selection: Use rules first, then LLM for tie-breaking
        """
        # First try rule-based
        selection = self._rule_based_selection(capability, providers, context)
        
        # If multiple alternatives with same priority, could use LLM
        # For demo, just return rule-based result
        return selection
    
    def get_tool_pool(self, capability: str) -> List[str]:
        """Get all available tools for a capability"""
        tool_pool = self.tool_pools.get(capability, {})
        providers = tool_pool.get("providers", [])
        return [p["name"] for p in providers]
    
    def get_fallback_order(self, capability: str) -> List[str]:
        """Get fallback order for a capability"""
        fallback_order = self.fallback_config.get("fallback_order", {})
        return fallback_order.get(capability, self.get_tool_pool(capability))


# Singleton instance
_bigtool_instance: Optional[BigtoolPicker] = None


def get_bigtool() -> BigtoolPicker:
    """Get or create Bigtool singleton instance"""
    global _bigtool_instance
    if _bigtool_instance is None:
        _bigtool_instance = BigtoolPicker()
    return _bigtool_instance


if __name__ == "__main__":
    # Test Bigtool
    bigtool = BigtoolPicker()
    
    # Test OCR selection
    selection = bigtool.select("ocr", {"environment": "development", "document_quality": 0.8})
    print(f"OCR Selection: {selection.selected_tool} - {selection.reason}")
    
    # Test enrichment selection
    selection = bigtool.select("enrichment", {"environment": "production"})
    print(f"Enrichment Selection: {selection.selected_tool} - {selection.reason}")
