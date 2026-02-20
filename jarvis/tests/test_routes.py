import pytest
from fastapi.testclient import TestClient
from jarvis.main import app

def test_debug_endpoint():
    client = TestClient(app)
    response = client.get('/api/debug')
    assert response.status_code == 200
    assert 'git_sha' in response.json()
    assert 'routes_file' in response.json()
    assert 'main_file' in response.json()
    assert 'registered_paths' in response.json()
