import pytest
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlparse

import httpx
from mcp.shared.exceptions import McpError
from mcp.types import TextContent, Tool, Prompt, GetPromptResult, PromptMessage
from pydantic import AnyUrl

from .server import (
    extract_content_from_html,
    get_robots_txt_url,
    check_may_autonomously_fetch_url,
    fetch_url,
    Server,
    DEFAULT_USER_AGENT_AUTONOMOUS,
    DEFAULT_USER_AGENT_MANUAL,
)


def test_extract_content_from_html():
    # Test basic HTML to markdown conversion
    html = "<h1>Test</h1><p>This is a test</p>"
    result = extract_content_from_html(html)
    assert "# Test" in result
    assert "This is a test" in result

    # Test empty content
    with patch("readabilipy.simple_json.simple_json_from_html_string") as mock_simple_json:
        mock_simple_json.return_value = {"content": ""}
        result = extract_content_from_html("<html></html>")
        assert result == "<error>Page failed to be simplified from HTML</error>"


def test_get_robots_txt_url():
    # Test with string URL
    url = "https://example.com/page"
    result = get_robots_txt_url(url)
    assert result == "https://example.com/robots.txt"

    # Test with AnyUrl
    url_obj = AnyUrl(url)
    result = get_robots_txt_url(url_obj)
    assert result == "https://example.com/robots.txt"

    # Test with different URL formats
    urls = [
        ("https://example.com", "https://example.com/robots.txt"),
        ("http://test.org/path?query=1", "http://test.org/robots.txt"),
        ("https://sub.domain.com/path#fragment", "https://sub.domain.com/robots.txt"),
    ]
    for input_url, expected in urls:
        assert get_robots_txt_url(input_url) == expected


@pytest.mark.asyncio
async def test_check_may_autonomously_fetch_url():
    url = "https://example.com"
    user_agent = DEFAULT_USER_AGENT_AUTONOMOUS

    # Test successful case
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nAllow: /"
        
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        
        # Should not raise any exception
        await check_may_autonomously_fetch_url(url, user_agent)

    # Test when robots.txt forbids access
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "User-agent: *\nDisallow: /"
        
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        
        with pytest.raises(McpError) as exc_info:
            await check_may_autonomously_fetch_url(url, user_agent)
        assert "autonomous fetching of this page is not allowed" in str(exc_info.value)

    # Test connection error
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.HTTPError("Connection failed")
        )
        
        with pytest.raises(McpError) as exc_info:
            await check_may_autonomously_fetch_url(url, user_agent)
        assert "Failed to fetch robots.txt" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_url():
    url = "https://example.com"
    user_agent = DEFAULT_USER_AGENT_AUTONOMOUS

    # Test HTML content
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><h1>Test</h1></body></html>"
        mock_response.headers = {"content-type": "text/html"}
        
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        
        content, prefix = await fetch_url(url, user_agent)
        assert "Test" in content
        assert prefix == ""

    # Test raw content
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Raw content"
        mock_response.headers = {"content-type": "text/plain"}
        
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        
        content, prefix = await fetch_url(url, user_agent, force_raw=True)
        assert content == "Raw content"
        assert "Content type" in prefix

    # Test error response
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.HTTPError("Connection failed")
        )
        
        with pytest.raises(McpError) as exc_info:
            await fetch_url(url, user_agent)
        assert "Failed to fetch" in str(exc_info.value)
