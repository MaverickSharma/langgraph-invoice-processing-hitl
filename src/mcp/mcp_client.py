"""
MCP (Model Context Protocol) Client
Orchestrates communication with COMMON and ATLAS servers
"""
from typing import Dict, Any, Optional, List
from enum import Enum
import requests
import structlog
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

logger = structlog.get_logger()


class MCPServer(str, Enum):
    """MCP Server types"""
    COMMON = "COMMON"
    ATLAS = "ATLAS"


class MCPAbility(str, Enum):
    """Available MCP abilities"""
    # COMMON Server abilities
    VALIDATE_SCHEMA = "validate_schema"
    NORMALIZE_VENDOR = "normalize_vendor"
    COMPUTE_FLAGS = "compute_flags"
    COMPUTE_MATCH_SCORE = "compute_match_score"
    BUILD_ACCOUNTING_ENTRIES = "build_accounting_entries"
    PERSIST_STATE = "persist_state"
    
    # ATLAS Server abilities
    OCR_EXTRACT = "ocr_extract"
    ENRICH_VENDOR = "enrich_vendor"
    FETCH_PO = "fetch_po"
    FETCH_GRN = "fetch_grn"
    FETCH_HISTORY = "fetch_history"
    APPLY_APPROVAL_POLICY = "apply_approval_policy"
    POST_TO_ERP = "post_to_erp"
    SCHEDULE_PAYMENT = "schedule_payment"
    NOTIFY_VENDOR = "notify_vendor"
    NOTIFY_FINANCE_TEAM = "notify_finance_team"


class MCPClient:
    """
    MCP Client for routing abilities to appropriate servers
    """
    
    def __init__(self):
        """Initialize MCP client with server configurations"""
        self.common_url = os.getenv("COMMON_SERVER_URL", "http://localhost:8001/mcp")
        self.atlas_url = os.getenv("ATLAS_SERVER_URL", "http://localhost:8002/mcp")
        self.timeout = int(os.getenv("MCP_TIMEOUT", "30"))
        
        # Ability routing map
        self.ability_routing = {
            # COMMON Server
            MCPAbility.VALIDATE_SCHEMA: MCPServer.COMMON,
            MCPAbility.NORMALIZE_VENDOR: MCPServer.COMMON,
            MCPAbility.COMPUTE_FLAGS: MCPServer.COMMON,
            MCPAbility.COMPUTE_MATCH_SCORE: MCPServer.COMMON,
            MCPAbility.BUILD_ACCOUNTING_ENTRIES: MCPServer.COMMON,
            MCPAbility.PERSIST_STATE: MCPServer.COMMON,
            
            # ATLAS Server
            MCPAbility.OCR_EXTRACT: MCPServer.ATLAS,
            MCPAbility.ENRICH_VENDOR: MCPServer.ATLAS,
            MCPAbility.FETCH_PO: MCPServer.ATLAS,
            MCPAbility.FETCH_GRN: MCPServer.ATLAS,
            MCPAbility.FETCH_HISTORY: MCPServer.ATLAS,
            MCPAbility.APPLY_APPROVAL_POLICY: MCPServer.ATLAS,
            MCPAbility.POST_TO_ERP: MCPServer.ATLAS,
            MCPAbility.SCHEDULE_PAYMENT: MCPServer.ATLAS,
            MCPAbility.NOTIFY_VENDOR: MCPServer.ATLAS,
            MCPAbility.NOTIFY_FINANCE_TEAM: MCPServer.ATLAS,
        }
        
        logger.info(
            "mcp_client_initialized",
            common_url=self.common_url,
            atlas_url=self.atlas_url
        )
    
    def execute_ability(
        self,
        ability: MCPAbility,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute an ability on the appropriate MCP server
        
        Args:
            ability: The ability to execute
            payload: Input data for the ability
            context: Additional context (workflow_id, stage_id, etc.)
        
        Returns:
            Response from the MCP server
        """
        server = self.ability_routing.get(ability)
        if not server:
            raise ValueError(f"Unknown ability: {ability}")
        
        logger.info(
            "executing_ability",
            ability=ability.value,
            server=server.value,
            context=context
        )
        
        # Route to appropriate server
        if server == MCPServer.COMMON:
            return self._call_common_server(ability, payload, context)
        elif server == MCPServer.ATLAS:
            return self._call_atlas_server(ability, payload, context)
        else:
            raise ValueError(f"Unknown server: {server}")
    
    def _call_common_server(
        self,
        ability: MCPAbility,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call COMMON server ability"""
        return self._make_request(
            url=self.common_url,
            ability=ability,
            payload=payload,
            context=context
        )
    
    def _call_atlas_server(
        self,
        ability: MCPAbility,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call ATLAS server ability"""
        return self._make_request(
            url=self.atlas_url,
            ability=ability,
            payload=payload,
            context=context
        )
    
    def _make_request(
        self,
        url: str,
        ability: MCPAbility,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to MCP server
        In production, this would use actual MCP protocol
        For demo, we mock the responses
        """
        request_data = {
            "ability": ability.value,
            "payload": payload,
            "context": context or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            # For demo, use mock implementation instead of actual HTTP
            return self._mock_mcp_response(ability, payload, context)
            
            # In production, uncomment this:
            # response = requests.post(
            #     url,
            #     json=request_data,
            #     timeout=self.timeout
            # )
            # response.raise_for_status()
            # return response.json()
            
        except Exception as e:
            logger.error(
                "mcp_request_failed",
                ability=ability.value,
                error=str(e)
            )
            raise
    
    def _mock_mcp_response(
        self,
        ability: MCPAbility,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Mock MCP server responses for demo
        In production, remove this and use actual MCP servers
        """
        logger.info("using_mock_mcp_response", ability=ability.value)
        
        # Import mock implementations
        from .common_server import execute_common_ability
        from .atlas_server import execute_atlas_ability
        
        server = self.ability_routing.get(ability)
        
        if server == MCPServer.COMMON:
            return execute_common_ability(ability, payload, context)
        elif server == MCPServer.ATLAS:
            return execute_atlas_ability(ability, payload, context)
        else:
            return {"success": False, "error": "Unknown server"}
    
    def health_check(self) -> Dict[str, bool]:
        """Check health of MCP servers"""
        return {
            "common": self._check_server_health(self.common_url),
            "atlas": self._check_server_health(self.atlas_url)
        }
    
    def _check_server_health(self, url: str) -> bool:
        """Check if server is healthy"""
        try:
            # For demo, always return True
            # In production, make actual health check request
            return True
        except Exception:
            return False


# Singleton instance
_mcp_client_instance: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """Get or create MCP client singleton"""
    global _mcp_client_instance
    if _mcp_client_instance is None:
        _mcp_client_instance = MCPClient()
    return _mcp_client_instance
