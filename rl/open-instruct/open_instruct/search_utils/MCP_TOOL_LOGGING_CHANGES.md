# MCP Tool 调用日志记录功能修改说明

## 修改概述

本次修改为 `MCPTool` 类添加了工具调用日志记录功能，用于记录前100次工具调用的详细信息，方便调试和验证工具调用是否正确。

## 修改文件

- `rl/open-instruct/open_instruct/search_utils/mcp_tools.py`

## 详细修改内容

### 1. 导入新的依赖模块

**位置**: 文件开头（第11-13行）

**修改前**:
```python
import httpx
import httpcore
```

**修改后**:
```python
import httpx
import httpcore
import json
import threading
from datetime import datetime
```

**原因**:
- `json`: 用于将日志记录序列化为JSON格式保存到文件
- `threading`: 用于线程安全的计数器，因为工具调用可能在多线程环境中执行
- `datetime`: 用于记录每次调用的时间戳

---

### 2. 添加全局计数器和锁

**位置**: 第60-63行（在 `MCPTool` 类定义之前）

**新增代码**:
```python
# Class-level counter and lock for thread-safe logging
_call_counter = 0
_call_counter_lock = threading.Lock()
_max_logged_calls = 100
```

**原因**:
- `_call_counter`: 全局计数器，跟踪已记录的工具调用次数
- `_call_counter_lock`: 线程锁，确保在多线程环境下计数器的原子操作
- `_max_logged_calls`: 最大记录次数常量，设置为100次
- 使用类级别变量而不是实例变量，因为可能有多个 `MCPTool` 实例，我们希望全局只记录前100次调用

---

### 3. 添加 `tool_log_dir` 参数

**位置**: `MCPTool.__init__` 方法参数列表（第90行）

**修改前**:
```python
def __init__(
    self,
    mcp_tool_names: List[str] | str,
    mcp_parser_name: str = "unified",
    # ... 其他参数 ...
    context_chars: int = 6000,
    *args,
    **kwargs,
):
```

**修改后**:
```python
def __init__(
    self,
    mcp_tool_names: List[str] | str,
    mcp_parser_name: str = "unified",
    # ... 其他参数 ...
    context_chars: int = 6000,
    tool_log_dir: str | None = None,  # 新增参数
    *args,
    **kwargs,
):
```

**原因**: 
- 允许用户显式指定日志目录
- 如果未指定，会通过其他方式自动确定（见下一节）

---

### 4. 初始化日志目录和文件路径

**位置**: `MCPTool.__init__` 方法内部（第96-109行）

**修改前**:
```python
self.mcp_tools = []
self.stop_strings = []
# Allow selecting transport via arg or env; default to StreamableHttpTransport
```

**修改后**:
```python
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
```

**原因**:
- **优先级设计**: 按照参数 > 环境变量 > kwargs中的output_dir > 默认值的顺序确定日志目录
  - 首先检查 `tool_log_dir` 参数（用户显式指定）
  - 其次检查 `MCP_TOOL_LOG_DIR` 环境变量（方便通过环境变量配置）
  - 然后检查 `kwargs` 中的 `output_dir`（训练脚本通常会传递这个参数）
  - 最后使用默认值 `./mcp_tool_logs`
- **自动创建目录**: 使用 `os.makedirs(..., exist_ok=True)` 确保日志目录存在
- **日志文件路径**: 固定文件名为 `tool_calls_log.jsonl`，使用JSONL格式（每行一个JSON对象）
- **打印提示信息**: 让用户知道日志文件的位置和记录次数限制

---

### 5. 添加日志记录辅助方法

**位置**: `MCPTool` 类中，`get_stop_strings` 方法之后（第151-188行）

**新增代码**:
```python
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
```

**原因**:
- **封装日志逻辑**: 将日志记录逻辑提取到独立方法，避免代码重复
- **参数说明**:
  - `call_number`: 调用序号（0-99）
  - `should_log`: 是否需要记录（前100次为True）
  - `tool_used_name`: 使用的工具名称
  - `trunc_prompt`: 处理后的输入提示
  - `text_output`: 格式化后的输出文本
  - `document_tool_output`: 原始工具输出对象
  - `error`: 错误信息
  - `found_tool`: 是否找到并调用了工具
  - `call_start_time`: 调用开始时间（用于计算总耗时）
- **日志字段设计**:
  - `call_number`: 调用序号，方便排序和查找
  - `timestamp`: ISO格式时间戳，精确到毫秒
  - `tool_name`: 工具名称，如 `google_search`、`snippet_search` 等
  - `success`: 是否成功（工具被调用且没有错误）
  - `input_prompt`: 输入的前1000字符（快速预览）
  - `full_input_prompt`: 完整输入，超过2000字符会截断
  - `output_text`: 输出的前2000字符（快速预览）
  - `full_output_text`: 完整输出，超过5000字符会截断
  - `error`: 错误信息（如果有）
  - `timeout`: 是否超时
  - `runtime`: 工具执行时间（来自工具本身）
  - `call_duration`: 总调用时长（包括重试等开销）
  - `called`: 是否实际调用了工具
- **文本截断**: 为了避免日志文件过大，对长文本进行截断，但保留完整版本字段
- **错误处理**: 使用 try-except 捕获日志写入错误，避免影响工具调用本身
- **编码设置**: 使用 `encoding="utf-8"` 和 `ensure_ascii=False` 支持中文等非ASCII字符

---

### 6. 修改 `__call__` 方法 - 添加调用计数和开始时间

**位置**: `MCPTool.__call__` 方法开头（第190-209行）

**修改前**:
```python
def __call__(self, prompt: str) -> ToolOutput:
    # the one thing open-instruct needs to do: remove older tool calls.
    trunc_prompt = truncate_at_second_last_stop(prompt, self.stop_strings)
    # work out which mcp tool to call.
    document_tool_output = None
    error = None
    found_tool = False
    text_output = ""
    tool_used_name = None
    try:
```

**修改后**:
```python
def __call__(self, prompt: str) -> ToolOutput:
    # the one thing open-instruct needs to do: remove older tool calls.
    trunc_prompt = truncate_at_second_last_stop(prompt, self.stop_strings)
    # work out which mcp tool to call.
    document_tool_output = None
    error = None
    found_tool = False
    text_output = ""
    tool_used_name = None
    call_start_time = time.time()  # 新增：记录开始时间
    
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
```

**原因**:
- **记录开始时间**: `call_start_time = time.time()` 用于后续计算总调用时长
- **线程安全的计数器**: 
  - 使用 `with _call_counter_lock:` 确保计数器的原子操作
  - 检查 `_call_counter < _max_logged_calls` 判断是否需要记录
  - 如果需要记录，保存当前计数器值并递增
  - `should_log` 标志用于后续判断是否写入日志

---

### 7. 修改 `__call__` 方法 - 在错误返回路径添加日志

**位置**: `MCPTool.__call__` 方法中，错误处理部分（第237-260行）

**修改前**:
```python
if document_tool_output is None:
    if error is None and not found_tool:
        error = "No valid tool calls found."
        print(f"MCP Tool Error: {error}")
        return ToolOutput(...)
    elif error is not None:
        print(f"MCP {tool_used_name} with {trunc_prompt} Tool Error: {error}")
        return ToolOutput(...)
    else:
        print(f"MCP {tool_used_name} Tool Error: Unknown error, no MCP response and no error found.")
        return ToolOutput(...)
```

**修改后**:
```python
if document_tool_output is None:
    if error is None and not found_tool:
        error = "No valid tool calls found."
        print(f"MCP Tool Error: {error}")
        self._log_tool_call(call_number, should_log, tool_used_name, trunc_prompt, text_output, None, error, found_tool, call_start_time)
        return ToolOutput(...)
    elif error is not None:
        print(f"MCP {tool_used_name} with {trunc_prompt} Tool Error: {error}")
        self._log_tool_call(call_number, should_log, tool_used_name, trunc_prompt, text_output, None, error, found_tool, call_start_time)
        return ToolOutput(...)
    else:
        print(f"MCP {tool_used_name} Tool Error: Unknown error, no MCP response and no error found.")
        self._log_tool_call(call_number, should_log, tool_used_name, trunc_prompt, text_output, None, "Unknown error, no MCP response and no error found.", found_tool, call_start_time)
        return ToolOutput(...)
```

**原因**:
- **记录错误情况**: 即使工具调用失败，也要记录日志，方便调试
- **统一日志接口**: 所有返回路径都调用 `_log_tool_call`，确保日志一致性
- **错误信息记录**: 将错误信息传递给日志方法，保存到日志文件中

---

### 8. 修改 `__call__` 方法 - 在成功返回路径添加日志

**位置**: `MCPTool.__call__` 方法末尾，成功返回前（第262-275行）

**修改前**:
```python
if document_tool_output.error:
    print(f"MCP {tool_used_name} Tool Error: {document_tool_output.error}")
    print("Returning error output anyway.")
# munge into format that open-instruct likes.
return ToolOutput(...)
```

**修改后**:
```python
if document_tool_output.error:
    print(f"MCP {tool_used_name} Tool Error: {document_tool_output.error}")
    print("Returning error output anyway.")

# Log tool call details for first 100 calls
self._log_tool_call(call_number, should_log, tool_used_name, trunc_prompt, text_output, document_tool_output, error, found_tool, call_start_time)

# munge into format that open-instruct likes.
return ToolOutput(...)
```

**原因**:
- **记录成功调用**: 工具调用成功时也要记录日志
- **记录位置**: 在返回前记录，此时所有信息都已准备好
- **包含完整信息**: 即使工具返回了错误（如搜索结果为空），也会记录，因为这是工具的正常行为

---

## 修改总结

### 新增功能
1. ✅ 记录前100次工具调用的详细信息
2. ✅ 线程安全的计数器机制
3. ✅ JSONL格式日志文件
4. ✅ 自动日志目录管理
5. ✅ 完整的错误和成功情况记录

### 修改的文件
- `rl/open-instruct/open_instruct/search_utils/mcp_tools.py`

### 新增的代码行数
- 约 120 行代码（包括注释和空行）

### 向后兼容性
- ✅ 完全向后兼容，所有新参数都有默认值
- ✅ 不影响现有功能，日志记录是可选的
- ✅ 如果日志写入失败，不会影响工具调用本身

---

## 使用示例

### 查看日志文件

```bash
# 查看日志文件位置（训练时会打印）
# 输出示例: 📝 MCP Tool call logs will be saved to: output/mcp_tool_logs/tool_calls_log.jsonl (first 100 calls)

# 查看前10条记录
head -n 10 output/mcp_tool_logs/tool_calls_log.jsonl | jq

# 查看所有成功的调用
cat output/mcp_tool_logs/tool_calls_log.jsonl | jq 'select(.success == true)'

# 查看所有失败的调用
cat output/mcp_tool_logs/tool_calls_log.jsonl | jq 'select(.success == false)'

# 查看特定工具的调用
cat output/mcp_tool_logs/tool_calls_log.jsonl | jq 'select(.tool_name == "google_search")'

# 统计各工具调用次数
cat output/mcp_tool_logs/tool_calls_log.jsonl | jq -r '.tool_name' | sort | uniq -c
```

### 日志文件格式示例

```json
{
  "call_number": 0,
  "timestamp": "2025-01-09T10:30:45.123456",
  "tool_name": "google_search",
  "success": true,
  "input_prompt": "<tool name=\"google_search\">machine learning</tool>",
  "full_input_prompt": "<tool name=\"google_search\">machine learning</tool>",
  "output_text": "Search results: ...",
  "full_output_text": "Search results: [详细结果]",
  "error": null,
  "timeout": false,
  "runtime": 1.234,
  "call_duration": 1.256,
  "called": true
}
```

---

## 故障排查

### 如果日志没有生成

1. **检查日志目录权限**: 确保有写入权限
2. **检查环境变量**: 确认 `MCP_TOOL_LOG_DIR` 或 `output_dir` 是否正确设置
3. **检查调用次数**: 只有前100次调用会被记录
4. **查看控制台输出**: 训练开始时会打印日志文件路径

### 如果日志文件过大

- 日志会自动截断长文本（输入2000字符，输出5000字符）
- 如果仍太大，可以修改 `_max_logged_calls` 常量减少记录次数
- 或者修改截断长度限制

### 如果需要修改记录次数

**位置**: 第63行
```python
_max_logged_calls = 100  # 修改这个值
```

### 如果需要修改日志目录

**方式1**: 通过参数传递
```python
tool = MCPTool(..., tool_log_dir="/path/to/logs")
```

**方式2**: 通过环境变量
```bash
export MCP_TOOL_LOG_DIR=/path/to/logs
```

**方式3**: 通过 output_dir（训练脚本会自动使用）
```python
# 训练脚本中，如果传递了 output_dir，会自动使用 output_dir/mcp_tool_logs
```

---

## 注意事项

1. **线程安全**: 使用 `threading.Lock()` 确保多线程环境下的安全性
2. **性能影响**: 日志记录对性能影响很小，因为：
   - 只记录前100次调用
   - 使用追加模式写入文件
   - 错误处理不会影响主流程
3. **磁盘空间**: 每条日志记录约1-10KB，100条记录约100KB-1MB
4. **日志格式**: 使用JSONL格式，方便逐行解析和处理

---

## 相关代码位置索引

- **全局计数器**: 第61-63行
- **日志目录初始化**: 第96-109行
- **日志记录方法**: 第151-188行
- **调用计数逻辑**: 第201-209行
- **错误路径日志**: 第237-260行
- **成功路径日志**: 第262-275行

---

**最后更新**: 2025-01-09
**修改人**: AI Assistant
**版本**: 1.0

