"""Supplier document APIs, behind one small interface.

Some suppliers publish their dockets and invoices through an API instead of
email. The register lists what a supplier has published for a job, downloads
each PDF it has not saved before, and puts it in the same inbox as everything
else: read by the supplier's parser, recorded only when a person confirms it.

The demo runs on SyntheticFeed, which reads `supplier_feed` - the build's
stand-in for the supplier's system. A real client is the same two calls over
the supplier's REST API (list documents for a job, download one by id), with
its token in Key Vault. This demo has never called a real supplier API.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.app.services import db


class SupplierFeed(Protocol):
    supplier: str

    def list_documents(self, project_id: str) -> list[dict[str, Any]]: ...
    def download(self, external_ref: str) -> bytes: ...


class SyntheticFeed:
    def __init__(self, supplier: str) -> None:
        self.supplier = supplier

    def list_documents(self, project_id: str) -> list[dict[str, Any]]:
        return db.raw("""SELECT external_ref, project_id, register, kind, filename, published_at FROM supplier_feed
                         WHERE supplier = ? AND project_id = ? ORDER BY published_at, external_ref""", [self.supplier, project_id])

    def download(self, external_ref: str) -> bytes:
        found = db.raw("SELECT pdf FROM supplier_feed WHERE supplier = ? AND external_ref = ?", [self.supplier, external_ref])
        if not found:
            raise LookupError(f"{self.supplier} has no document {external_ref}")
        return bytes(found[0]["pdf"])


def suppliers() -> list[str]:
    """Suppliers that publish through an API."""
    return [r["supplier"] for r in db.raw("SELECT DISTINCT supplier FROM supplier_feed ORDER BY 1")]


def client(supplier: str) -> SupplierFeed:
    return SyntheticFeed(supplier)
