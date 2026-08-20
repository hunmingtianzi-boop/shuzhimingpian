from __future__ import annotations

from app.main import app


def test_implemented_vertical_slice_uses_contract_operation_ids() -> None:
    paths = app.openapi()["paths"]
    expected = {
        ("/api/v1/health/live", "get"): "getLiveness",
        ("/api/v1/health/ready", "get"): "getReadiness",
        ("/api/v1/public/cards/{slug}", "get"): "getPublicCard",
        ("/api/v1/public/cards/{slug}/visits", "post"): "createVisit",
        ("/api/v1/public/cards/{slug}/consents", "post"): "recordConsent",
        ("/api/v1/public/cards/{slug}/conversations", "post"): "createConversation",
        (
            "/api/v1/public/conversations/{conversation_id}/messages:stream",
            "post",
        ): "streamConversationMessage",
        ("/api/v1/auth/login", "post"): "login",
        ("/api/v1/auth/refresh", "post"): "refreshStaffSession",
        ("/api/v1/auth/logout", "post"): "logoutStaffSession",
        ("/api/v1/auth/me", "get"): "getCurrentUser",
        ("/api/v1/admin/entitlements", "get"): "getAdminCommercialEntitlements",
        (
            "/api/v1/platform/enterprises/{company_id}/entitlements",
            "get",
        ): "getPlatformEnterpriseEntitlements",
        (
            "/api/v1/platform/enterprises/{company_id}/entitlements",
            "put",
        ): "updatePlatformEnterpriseEntitlements",
        ("/api/v1/admin/company/profile", "get"): "getCompanyProfile",
        ("/api/v1/admin/company/profile", "put"): "updateCompanyProfile",
        ("/api/v1/admin/card", "get"): "getAdminCard",
        ("/api/v1/admin/card", "put"): "updateAdminCard",
        ("/api/v1/admin/dashboard", "get"): "getAdminDashboard",
        (
            "/api/v1/admin/analytics/employees",
            "get",
        ): "listEmployeeAnalytics",
        ("/api/v1/admin/knowledge/documents", "get"): "listKnowledgeDocuments",
        ("/api/v1/admin/knowledge/documents", "post"): "createKnowledgeDocument",
        (
            "/api/v1/admin/knowledge/documents/{document_id}",
            "get",
        ): "getKnowledgeDocument",
        (
            "/api/v1/admin/knowledge/documents/{document_id}",
            "put",
        ): "putKnowledgeDocumentDraft",
        (
            "/api/v1/admin/knowledge/documents/{document_id}",
            "delete",
        ): "deleteKnowledgeDocument",
        (
            "/api/v1/admin/knowledge/documents/{document_id}/publish",
            "post",
        ): "publishKnowledgeDocument",
    }

    for (path, method), operation_id in expected.items():
        assert paths[path][method]["operationId"] == operation_id
