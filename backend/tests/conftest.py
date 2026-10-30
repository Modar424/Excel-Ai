import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_spec_provider
from app.core.config import Settings
from app.main import create_app
from app.schemas.spreadsheet import ColumnSpec, SheetSpec, WorkbookSpec


class MockProvider:
    def __init__(self, spec=None, exc=None, delay=0):
        self.spec, self.exc, self.delay = spec, exc, delay

    async def generate_spec(self, prompt, language, max_rows):
        if self.delay:
            import asyncio
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.spec


def sample_spec(title="Employees") -> WorkbookSpec:
    return WorkbookSpec(title=title, sheets=[SheetSpec(
        title="Data", columns=[ColumnSpec(name="Name"), ColumnSpec(name="Salary", type="currency")],
        rows=[["Template A", 100], ["=1+1", 200]])])


def make_client(provider=None, **overrides):
    base = dict(groq_api_key="x", cors_origins="http://localhost:5173", rate_limit_per_min=1000)
    s = Settings(_env_file=None, **{**base, **overrides})
    app = create_app(s)
    if provider is not None:
        app.dependency_overrides[get_spec_provider] = lambda: provider
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client():
    return make_client(MockProvider(sample_spec()))
