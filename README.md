# Cortex Agents and Slack

## About This Project

This repository is a refactored version of [sfguide-integrate-snowflake-cortex-agents-with-slack](https://github.com/Snowflake-Labs/sfguide-integrate-snowflake-cortex-agents-with-slack).

### Major changes from the original:
- Multi-Model Support: The Cortex Chat class now accepts lists of semantic models and search services.
- First-Use Warning: Added an AI disclaimer that shows once per day per user to set appropriate expectations
- Refactored charting, which is still WIP. 
- Other small misc. changes to meet my immediate needs for implementation.

### Multi-Model Details
Set environment variables for multiple semantic models and search services:

``` ini
# Environment variables (.env file)
SUPPORT_TICKETS_SEMANTIC_MODEL=@DASH_DB.DASH_SCHEMA.DASH_SEMANTIC_MODELS/support_tickets_semantic_model.yaml
INVENTORY_SEMANTIC_MODEL=@DASH_DB.DASH_SCHEMA.DASH_SEMANTIC_MODELS/inventory_semantic_model.yaml
VEHICLE_SEARCH_SERVICE=DASH_DB.DASH_SCHEMA.vehicles_info
INVENTORY_SEARCH_SERVICE=DASH_DB.DASH_SCHEMA.inventory_info
```
Any environment variable ending with _SEMANTIC_MODEL or _SEARCH_SERVICE will be detected and used.

```python

def init():
    # ... code ...

    # Collect semantic models 
    semantic_models = []

    # Look for any other environment variables ending with _SEMANTIC_MODEL
    for key, value in os.environ.items():
        if key.endswith("_SEMANTIC_MODEL") and key != "SUPPORT_TICKETS_SEMANTIC_MODEL" and value:
            model = value.strip()
            if model and model not in semantic_models:
                semantic_models.append(model)
                print(f"Found additional semantic model ({key}): {model}")

    # Collect search services 
    search_services = []
    
    # Look for any other environment variables ending with _SEARCH_SERVICE
    for key, value in os.environ.items():
        if key.endswith("_SEARCH_SERVICE") and key != "PRIMARY_SEARCH_SERVICE" and value:
            service = value.strip()
            if service and service not in search_services:
                search_services.append(service)
                print(f"Found additional search service ({key}): {service}")

    # ... rest of code ...

```

When setting up the CortexChat instance, both lists are passed to the constructor:

```python
cortex_app = CortexChat(
    agent_url=AGENT_ENDPOINT,
    search_services=search_services,
    semantic_models=semantic_models,
    model=MODEL,
    account=ACCOUNT,
    user=USER,
    private_key_path=RSA_PRIVATE_KEY_PATH
)
```

## Quickstart Guide and Original Project

For prerequisites, environment setup, step-by-step guide and instructions, please refer to the [QuickStart Guide](https://quickstarts.snowflake.com/guide/integrate_snowflake_cortex_agents_with_slack/index.html).
