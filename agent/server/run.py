#!/usr/bin/env python3
"""
Server entry point for the DR-Tulu Chat API.

Usage:
    python -m server.run --config workflows/auto_search_sft.yaml --port 8080
"""

import argparse
import sys
from pathlib import Path

import uvicorn

# Add agent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.api import app, set_workflow
from workflows.auto_search_sft import AutoReasonSearchWorkflow


def main():
    parser = argparse.ArgumentParser(description="DR-Tulu Chat API Server")
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to workflow configuration YAML file (defaults to workflow's _default_configuration_path)",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=8080, help="Port to run the server on"
    )
    parser.add_argument(
        "--host", type=str, default="0.0.0.0", help="Host to bind the server to"
    )
    parser.add_argument(
        "--config-overrides",
        type=str,
        default=None,
        help="Config overrides in format 'param1=value1,param2=value2'",
    )
    args = parser.parse_args()

    # Parse config overrides
    overrides = {}
    if args.config_overrides:
        for pair in args.config_overrides.split(","):
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            key = key.strip()
            value = value.strip()

            if value.lower() == "true":
                overrides[key] = True
            elif value.lower() == "false":
                overrides[key] = False
            elif value.lower() in ["none", "null"]:
                overrides[key] = None
            elif value.isdigit():
                overrides[key] = int(value)
            else:
                try:
                    overrides[key] = float(value)
                except ValueError:
                    overrides[key] = value

    # Set reasonable defaults for interactive use
    if "browse_timeout" not in overrides:
        overrides["browse_timeout"] = 10
    if "prompt_version" not in overrides:
        overrides["prompt_version"] = "cli"

    # Use workflow's default config if not specified
    config_path = args.config or AutoReasonSearchWorkflow._default_configuration_path
    print(f"Loading workflow from: {config_path}")
    workflow = AutoReasonSearchWorkflow(configuration=config_path, **overrides)
    set_workflow(workflow)
    print("Workflow loaded successfully")

    print(f"Starting server at http://{args.host}:{args.port}")
    print(f"SSE endpoint: http://{args.host}:{args.port}/chat/stream")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
