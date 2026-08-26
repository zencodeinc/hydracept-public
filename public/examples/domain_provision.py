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
    "GET /v1/capabilities — public domain/DNS catalog (search, list, DNS CRUD, TLS, transfer)",
    "MCP hydracept_invoke domain.search.v1 — check availability (managed registrar by default)",
    "MCP hydracept_invoke dns.record.list.v1 — inspect records after registration",
    "POST /v1/capabilities/web.domain.provision.v1/jobs — submit outcome job",
    "approve purchase (domain, registrant, prices, registrar agreement) via unified job approval",
    "poll unified job status until succeeded or needs_attention",
    "optional: POST /v1/connections with registrar apiKey+secretKey for customer custody",
    "fetch unified job receipt for externalActions ledger summary",
]
