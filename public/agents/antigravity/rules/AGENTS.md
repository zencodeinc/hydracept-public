---
trigger: always_on
---

# Hydracept directory connector

- Authenticate only through the plugin OAuth flow. Never ask the user to paste a Hydracept API key into chat.
- Prefer `hydracept_status`, capability list/resolve, quote, and job-status tools before spending.
- This connector does not generate images, video, audio, or 3D.
- Do not invent provider model names; use capability keys returned by Hydracept tools.
