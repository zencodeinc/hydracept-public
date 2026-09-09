# Hydracept for Unity

Editor-only integration for generating and importing Hydracept production assets.

## Requirements

- Unity 6.0 or newer
- Hydracept CLI workspace configured in your project root

## Install

### Package Manager (Git URL)

```
https://github.com/zencodeinc/hydracept-public.git?path=/packages/unity#v0.1.0
```

### CLI

```bash
python -m hydracept integrations install unity
```

## Setup

From your Unity project root:

```bash
python -m hydracept init --apply --yes --json
```

Then in Unity: **Window → Hydracept → Refresh**.

## Usage

1. Open **Window → Hydracept**
2. Generate a sprite or Sheet & Slice set
3. Import artifacts into `Assets/Generated/Hydracept/`

Imported assets work offline. Player builds do not include Hydracept credentials or runtime code.
