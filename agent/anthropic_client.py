import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)


def get_anthropic_client() -> Anthropic:
    headers = {}
    workspace_id = os.getenv("ANTHROPIC_WORKSPACE_ID")
    if workspace_id:
        headers["anthropic-workspace-id"] = workspace_id
    return Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        default_headers=headers or None,
    )
