"""Explicit Windows-only integration check; temporary synthetic credential is removed."""
from uuid import uuid4
from backend.app.confluence.credentials import WindowsCredentials

if __name__ == "__main__":
    store=WindowsCredentials()
    key="test-"+str(uuid4())
    try:
        assert store.get(key) is None
        store.set(key,"synthetic-test-value")
        assert store.get(key)=="synthetic-test-value"
        store.set(key,"synthetic-replacement")
        assert store.get(key)=="synthetic-replacement"
    finally:
        store.delete(key)
    assert store.get(key) is None
    print("Windows Credential Manager set/read/replace/delete: PASS")
