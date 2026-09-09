"""Example: submit an image capability job via the Hydracept public API."""

EXAMPLE = {
    "context": {
        "productId": "your-project-id",
        "projectId": "your-customer-project-id",
        "environment": "development",
    },
    "input": {"prompt": "game icon, flat vector", "width": 1024, "height": 1024},
    "execution": {"executionPreference": "automatic"},
    "idempotencyKey": "example-image-1",
}
