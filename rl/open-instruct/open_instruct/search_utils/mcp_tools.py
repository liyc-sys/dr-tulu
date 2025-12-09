"""
A wrapper and registry for tools in rl-rag-mcp.
"""
from typing import List
import inspect
import asyncio
import os
import time
import httpx
import httpcore
import json
import threading
from datetime import datetime

try:
    from dr_agent.tool_interface.mcp_tools import MassiveServeSearchTool, SemanticScholarSnippetSearchTool, SerperSearchTool, Crawl4AIBrowseTool, SerperBrowseTool
except ImportError as e:
    print(f"Failed to import dr_agent. Please install it:\n{e}")
    raise e

from open_instruct.search_rewards.utils.format_utils import generate_snippet_id
from open_instruct.tool_utils.tool_vllm import Tool, ToolOutput

MCP_TOOL_REGISTRY = {
    "snippet_search": SemanticScholarSnippetSearchTool,
    "google_search": SerperSearchTool,
    "massive_serve": MassiveServeSearchTool,
    "browse_webpage": Crawl4AIBrowseTool,
    # "browse_webpage": SerperBrowseTool
}

def truncate_at_second_last_stop(text: str, stops: list[str]) -> str:
    # dedup stop strings
    stops = list(set(stops))
    # Collect all stop occurrences (position, stopstring)
    positions = []
    for stop in stops:
        start = 0
        while True:
            idx = text.find(stop, start)
            if idx == -1:
                break
            positions.append((idx, stop))
            start = idx + len(stop)

    # If fewer than 2 stops, return unchanged
    if len(positions) < 2:
        return text

    # Sort by position in the string
    positions.sort(key=lambda x: x[0])

    # Take the second-last occurrence
    idx, stop = positions[-2]

    # Remove everything up to and including this occurrence
    return text[idx + len(stop):]


# Class-level counter and lock for thread-safe logging
_call_counter = 0
_call_counter_lock = threading.Lock()
_max_logged_calls = 100


class MCPTool(Tool):
    """
    Unlike other tools, this guy handles *all mcp tools*. Why?
    because they share the same end string (</tool>). Hence, we need the parsers
    to work out how to route them. Ideally, this would be more tightly integrated into vllm,
    but for now, this is a bit cleaner.
    """
    def __init__(
        self,
        mcp_tool_names: List[str] | str,
        mcp_parser_name: str = "unified",
        transport_type: str | None = None,
        mcp_host: str | None = None,
        mcp_port: int | None = None,
        max_retries: int = 3,
        retry_backoff: float = 0.5,
        search_api_endpoint: str | None = None,
        start_str: str = "",
        end_str: str | None = None,
        mcp_timeout: int = 180,
        base_url: str | None = None,
        number_documents_to_search: int = 10,
        use_localized_snippets: bool = False,
        context_chars: int = 6000,
        tool_log_dir: str | None = None,
        *args,
        **kwargs,
    ):
        self.mcp_tools = []
        self.stop_strings = []
        # Setup logging directory for tool calls
        # Priority: tool_log_dir parameter > MCP_TOOL_LOG_DIR env > output_dir/mcp_tool_logs > ./mcp_tool_logs
        if tool_log_dir:
            self.tool_log_dir = tool_log_dir
        elif "MCP_TOOL_LOG_DIR" in os.environ:
            self.tool_log_dir = os.environ["MCP_TOOL_LOG_DIR"]
        elif "output_dir" in kwargs:
            # If output_dir is provided, use it as base directory
            self.tool_log_dir = os.path.join(kwargs["output_dir"], "mcp_tool_logs")
        else:
            self.tool_log_dir = "./mcp_tool_logs"
        os.makedirs(self.tool_log_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.tool_log_dir, "tool_calls_log.jsonl")
        print(f"📝 MCP Tool call logs will be saved to: {self.log_file_path} (first {_max_logged_calls} calls)")
        # Allow selecting transport via arg or env; default to StreamableHttpTransport
        self.transport_type = transport_type or os.environ.get("MCP_TRANSPORT", "StreamableHttpTransport")
        self.mcp_host = mcp_host or os.environ.get("MCP_TRANSPORT_HOST", "0.0.0.0")
        if self.mcp_host is not None:
            os.environ["MCP_TRANSPORT_HOST"] = str(self.mcp_host)
        self.mcp_port = mcp_port or os.environ.get("MCP_TRANSPORT_PORT", 8000)
        if self.mcp_port is not None:
            os.environ["MCP_TRANSPORT_PORT"] = str(self.mcp_port)
        # Transient error retry settings
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        # Support comma-separated string for mcp_tool_names
        if isinstance(mcp_tool_names, str):
            mcp_tool_names = [n.strip() for n in mcp_tool_names.split(",") if n.strip()]
        for mcp_tool_name in mcp_tool_names:
            # filter kwargs so we only pass ones the constructor understands
            mcp_tool_cls = MCP_TOOL_REGISTRY[mcp_tool_name]
            sig = inspect.signature(mcp_tool_cls.__init__)
            valid_params = set(sig.parameters.keys())
            filtered_kwargs = {
                k: v for k, v in kwargs.items() if k in valid_params
            }
            if "base_url" in valid_params:
                filtered_kwargs["base_url"] = base_url
            if "number_documents_to_search" in valid_params:
                filtered_kwargs["number_documents_to_search"] = number_documents_to_search
            if "use_localized_snippets" in valid_params:
                filtered_kwargs["use_localized_snippets"] = use_localized_snippets
            if "context_chars" in valid_params:
                filtered_kwargs["context_chars"] = context_chars
            # special case for crawl4ai
            if mcp_tool_name == "browse_webpage":
                filtered_kwargs["use_docker_version"] = True
                filtered_kwargs["use_ai2_config"] = True
            # basically, we want to defer as much as possible to the mcp tool.
            # this 'tool' actually just passes everything down to the mcp tool.
            self.mcp_tools.append(mcp_tool_cls(
                timeout=mcp_timeout,
                name=mcp_tool_name,
                tool_parser=mcp_parser_name,
                transport_type=self.transport_type,
                **filtered_kwargs,
            ))
            # assign the stop strings from the parser itself.
            self.stop_strings += self.mcp_tools[-1].tool_parser.stop_sequences
        # MCP tool handles its own start and end strings.
        super().__init__(start_str=start_str, end_str=end_str or self.stop_strings[-1])

    def get_stop_strings(self) -> List[str]:
        return self.stop_strings

    def _log_tool_call(
        self,
        call_number: int | None,
        should_log: bool,
        tool_used_name: str | None,
        trunc_prompt: str,
        text_output: str,
        document_tool_output,
        error: str | None,
        found_tool: bool,
        call_start_time: float,
    ):
        """Helper function to log tool call details."""
        if not should_log or call_number is None:
            return
        
        call_end_time = time.time()
        log_entry = {
            "call_number": call_number,
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_used_name,
            "success": found_tool and document_tool_output is not None,
            "input_prompt": trunc_prompt[:1000] if trunc_prompt else None,  # Truncate to avoid huge logs
            "full_input_prompt": trunc_prompt if len(trunc_prompt) <= 2000 else trunc_prompt[:2000] + "...[truncated]",
            "output_text": text_output[:2000] if text_output else None,  # Truncate output
            "full_output_text": text_output if text_output and len(text_output) <= 5000 else (text_output[:5000] + "...[truncated]" if text_output else None),
            "error": error or (document_tool_output.error if document_tool_output and document_tool_output.error else None),
            "timeout": document_tool_output.timeout if document_tool_output else False,
            "runtime": document_tool_output.runtime if document_tool_output else None,
            "call_duration": call_end_time - call_start_time,
            "called": found_tool,
        }
        
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as log_error:
            print(f"Warning: Failed to write tool call log: {log_error}")

    def __call__(self, prompt: str) -> ToolOutput:
        # the one thing open-instruct needs to do: remove older tool calls.
        trunc_prompt = truncate_at_second_last_stop(prompt, self.stop_strings)
        # work out which mcp tool to call.
        document_tool_output = None
        error = None
        found_tool = False
        text_output = ""
        tool_used_name = None
        call_start_time = time.time()
        
        # Get call number for logging
        global _call_counter
        should_log = False
        call_number = None
        with _call_counter_lock:
            if _call_counter < _max_logged_calls:
                call_number = _call_counter
                _call_counter += 1
                should_log = True
        
        try:
            for mcp_tool in self.mcp_tools:
                if mcp_tool.tool_parser.has_calls(trunc_prompt, mcp_tool.name):
                    # Retry on transient stream/network errors
                    last_exc: Exception | None = None
                    for attempt in range(self.max_retries):
                        try:
                            document_tool_output = asyncio.run(mcp_tool(trunc_prompt))
                            print("Using MCP tool: ", mcp_tool.name)
                            break
                        except (httpcore.RemoteProtocolError, httpx.ReadError, ConnectionError, TimeoutError, asyncio.TimeoutError) as e:
                            last_exc = e
                            print(f"{mcp_tool.name} Error: {e}, retrying...")
                            if attempt + 1 >= self.max_retries:
                                raise
                            time.sleep(self.retry_backoff * (2 ** attempt))
                    # first format the output
                    text_output = mcp_tool._format_output(document_tool_output)
                    # wrap in the tags
                    text_output = mcp_tool.tool_parser.format_result(text_output, document_tool_output)
                    found_tool = True
                    tool_used_name = mcp_tool.name
                    break
        except Exception as e:
            error = str(e)
        if document_tool_output is None:
            if error is None and not found_tool:
                error = "No valid tool calls found."
                print(f"MCP Tool Error: {error}")
                self._log_tool_call(call_number, should_log, tool_used_name, trunc_prompt, text_output, None, error, found_tool, call_start_time)
                return ToolOutput(
                    output=error,
                    called=False,
                    error=error,
                    timeout=False,
                    runtime=0,
                    start_str="<snippet id=" + generate_snippet_id() + ">\n",
                    end_str="\n</snippet>",
                )
            elif error is not None:
                print(f"MCP {tool_used_name} with {trunc_prompt} Tool Error: {error}")
                self._log_tool_call(call_number, should_log, tool_used_name, trunc_prompt, text_output, None, error, found_tool, call_start_time)
                return ToolOutput(
                    output=error,
                    called=False,
                    error=error,
                    timeout=False,
                    runtime=0,
                    start_str="<snippet id=" + generate_snippet_id() + ">\n",
                    end_str="\n</snippet>",
                )
            else:
                print(f"MCP {tool_used_name} Tool Error: Unknown error, no MCP response and no error found.")
                self._log_tool_call(call_number, should_log, tool_used_name, trunc_prompt, text_output, None, "Unknown error, no MCP response and no error found.", found_tool, call_start_time)
                return ToolOutput(
                    output="Unknown error, no MCP response and no error found.",
                    called=False,
                    error="Unknown error, no MCP response and no error found.",
                    timeout=False,
                    runtime=0,
                    start_str="<snippet id=" + generate_snippet_id() + ">\n",
                    end_str="\n</snippet>",
                )

        if document_tool_output.error:
            print(f"MCP {tool_used_name} Tool Error: {document_tool_output.error}")
            print("Returning error output anyway.")
        
        # Log tool call details for first 100 calls
        self._log_tool_call(call_number, should_log, tool_used_name, trunc_prompt, text_output, document_tool_output, error, found_tool, call_start_time)
        
        # munge into format that open-instruct likes.
        return ToolOutput(
            output=text_output,
            called=True,
            error=document_tool_output.error,
            timeout=document_tool_output.timeout,
            runtime=document_tool_output.runtime,
            start_str="\n",
            end_str="\n\n",
        )


if __name__ == "__main__":
    # example usage.
    from open_instruct.grpo_fast import launch_mcp_subprocess
    import time
    # need to launch mcp server first.
    launch_mcp_subprocess("python -m dr_agent.mcp_backend.main --transport http --port 8000 --host 0.0.0.0 --path /mcp", "./mcp_logs")
    # wait for it to launch.
    time.sleep(10)
    # then we can use the mcp tool.
    mcp_tool = MCPTool(["browse_webpage"], number_documents_to_search=10, api_endpoint="http://localhost:8000/mcp")
    print(mcp_tool('<tool name="browse_webpage">https://www.google.com</tool>'))

