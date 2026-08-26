# Reproducible research runs

Use [Pinned Execution](../pinned-execution/) when a research run needs an explicit provider, model, API, and request. The completed execution record captures the settings and provider response so a result can be reviewed and reproduced.

Group related runs in a [manifest](../provenance/) and save a stable setup in an AI lockfile. The public endpoint is:

```http
POST /v1/inference/pinned
GET  /v1/inference/pinned/{receipt_id}
```
