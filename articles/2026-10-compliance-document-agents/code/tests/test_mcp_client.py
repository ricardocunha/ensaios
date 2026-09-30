"""End-to-end: start the MCP server over stdio and call its tools, as an agent would."""

import json
import os
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

DATA = Path(__file__).parent / "fixtures"


@pytest.mark.anyio
async def test_tools_over_stdio():
    params = StdioServerParameters(command="uv", args=["run", "compliance-mcp"], env={**os.environ, "COMPLIANCE_DATA_DIR": str(DATA)})
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        names = {t.name for t in (await s.list_tools()).tools}
        assert {"list_documents", "parse_document", "get_section", "search_document", "verify_quote"} <= names
        docs = await s.call_tool("list_documents", {})
        assert "sample-contract" in docs.content[0].text
        hits = await s.call_tool("search_document", {"doc_id": "sample-contract", "query": "vigencia"})
        assert "VIGÊNCIA" in hits.content[0].text
        q = await s.call_tool("verify_quote", {"doc_id": "sample-contract", "quote": "prazo de  VIGENCIA de 12 (DOZE) meses"})
        assert json.loads(q.content[0].text)["found"] is True
        q = await s.call_tool("verify_quote", {"doc_id": "sample-contract", "quote": "prazo de 36 meses"})
        assert json.loads(q.content[0].text)["found"] is False


@pytest.fixture
def anyio_backend():
    return "asyncio"
