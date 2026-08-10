"""Example: provision a web domain via Hydracept infrastructure capabilities."""

EXAMPLE_SEARCH = {
    "context": {
        "productId": "your-project-id",
        "projectId": "your-customer-project-id",
        "environment": "development",
    },
    "input": {"domain": "hydrathing.com"},
    "execution": {"executionPreference": "automatic"},
}

EXAMPLE_PROVISION_JOB = {
    "context": {
        "productId": "your-project-id",
        "projectId": "your-customer-project-id",
        "environment": "development",
    },
    "input": {
        "domain": "hydrathing.com",
        "target": {
            "type": "static",
            "records": [
                {"type": "A", "name": "", "content": "192.0.2.1"},
                {"type": "CNAME", "name": "www", "content": "hydrathing.com"},
            ],
        },
    },
    "idempotencyKey": "example-provision-1",
}

FLOW = [
    "POST /v1/connections — store Porkbun BYOK (apiKey + secretKey)",
    "POST /v1/connections/{id}/bindings — bind to project/environment",
    "POST /v1/capabilities/domain.search.v1/invoke — check availability",
    "POST /v1/capabilities/web.domain.provision.v1/jobs — submit outcome job",
    "approve job with authorizedMaxAmount via unified job approval endpoint",
    "poll unified job status until succeeded or needs_attention",
    "fetch unified job receipt for externalActions ledger summary",
]
