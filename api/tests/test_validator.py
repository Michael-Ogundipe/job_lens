import pytest
from app.services.validator import validate_url

@pytest.mark.asyncio
async def test_missing_url():
    result = await validate_url(None)
    assert result["status"] == "UNKNOWN"
