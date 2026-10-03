# Python AI Agents: Build One Tonight Without LangChain Bloat

_Stop fighting massive frameworks—here is a raw, working loop using standard libraries and OpenAI tools._

## Scroll-stopping hooks

**Hook 1.** Spent four hours debugging a LangChain abstraction hell last night before deleting the whole folder and writing 40 lines of clean Python.

**Hook 2.** Most tutorials make AI agents sound like rocket science, but an agent is literally just a while loop with tool calls.

**Hook 3.** If your agent needs 12 wrapper classes just to search a database, you are overengineering the wrong layer.

**Hook 4.** Wrote my first production Python agent at 1 AM because I refused to install a 400MB dependency graph for a basic calculator.

**Hook 5.** You don't need a framework to build an autonomous agent—you just need the official OpenAI SDK and Python's inspect module.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to auto-generate JSON schemas from your Python functions
_Why it matters:_ It eliminates manual schema dicts and prevents subtle type mismatch bugs when the model picks a tool.

```python
from pydantic import TypeAdapter
schema = TypeAdapter(my_func).json_schema()
```

### Tip 2. Map function names directly to callables using a simple dictionary dispatch table
_Why it matters:_ It avoids ugly, unmaintainable if-elif chains inside your main inference loop.

```
tools_map = {'get_weather': get_weather, 'run_query': run_query}
result = tools_map[tool_name](**tool_args)
```

### Tip 3. Bind tool schemas with openai.pydantic_function_tool for cleaner setups
_Why it matters:_ The official SDK parses Pydantic models into valid tool definitions in one line.

```python
from openai import pydantic_function_tool
tool_def = pydantic_function_tool(SearchInput)
```

### Tip 4. Enforce a hard max_iterations cap on your execution while loop
_Why it matters:_ Without an explicit exit counter, an errant LLM will burn your API credits in an infinite call loop.

```
for _ in range(5):
    # run agent step
    if not response.tool_calls: break
```

### Tip 5. Format execution errors as regular tool output messages instead of throwing exceptions
_Why it matters:_ Passing the traceback back into the conversation lets the model correct its own mistakes.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': f'Error: {err}'})
```

### Tip 6. Use rich.console to print live tool execution and thoughts during development
_Why it matters:_ It lets you instantly see when the agent is looping or sending bad arguments without checking logs.

```python
from rich import print
print(f'[yellow]Running {tool_name}[/] with {tool_args}')
```

### Tip 7. Track total token counts after each iteration using response.usage
_Why it matters:_ Tool-heavy agent loops can blow past context limits in just three or four turns.

```
prompt_tokens += response.usage.prompt_tokens
```

## Step-by-step procedure

### 1. Install the official OpenAI and Pydantic packages
Keep your environment clean—avoid monolithic wrapper libraries that hide API mechanics.

```python
pip install openai pydantic
```

### 2. Define a plain Python tool function and its schema
Write the function that performs the action and define its inputs using standard type hints.

```python
def add_numbers(a: int, b: int) -> int:
    return a + b
```

### 3. Register the tool definition with the OpenAI tool format
Pass the JSON schema so the model knows what arguments it needs to extract.

```
tools = [{'type': 'function', 'function': {'name': 'add_numbers', 'parameters': {'type': 'object', 'properties': {'a': {'type': 'integer'}, 'b': {'type': 'integer'}}, 'required': ['a', 'b']}}}]
```

### 4. Build the while loop to handle tool executions
Send messages to the model, parse tool calls, execute your local function, and append the result.

```
response = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tools)
```

### 5. Run the script with a prompt that requires calculation
Test the pipeline with a prompt like 'What is 143 plus 928?' and confirm the function executes locally before the final answer prints.

```
python agent.py
```

## The mistake almost everyone makes

> ⚠️  Forgetting to send the assistant message containing the tool_calls list back to the API before sending the tool response, which triggers an immediate 400 Bad Request error. Fix it by appending the raw assistant response message to your history first.

## X / Twitter thread (copy-paste ready)

**1/** You don't need a massive framework to build an AI agent in Python. Here is the actual architecture in 6 tweets.

**2/** Wasted 3 hours last night fighting dependency hell. Agents aren't magic—they are just a while loop passing JSON back and forth with an LLM.

**3/** 1. Define plain Python functions for tools and map them in a dictionary: `tools_map = {'search': search_fn}`. No wrapper classes needed.

**4/** 2. Pass the JSON schema to OpenAI. When `response.choices[0].message.tool_calls` appears, parse the arguments using `json.loads`.

**5/** 3. Execute the function locally and push the result back into `messages` with role='tool'. Catch errors and pass the string back so the LLM can self-heal.

**6/** Put a `max_steps=5` guardrail on your loop so you don't burn cash. Try building one from scratch tonight—it takes 40 lines of code.

## LinkedIn version

At 1 AM last night, I had 14 browser tabs open trying to figure out why an agent library kept swallowing my exceptions inside an opaque execution chain.

I got annoyed, deleted the virtualenv, and decided to build the agent from scratch using just the official OpenAI client and native Python.

Turns out, a practical AI agent is roughly 40 lines of code. It is an LLM call inside a while loop. If the model returns tool calls, you run your local functions, append the results to the message history, and call the model again. If it returns text, you break the loop.

You don't need heavyweight abstractions that hide what is actually going on. Writing the raw loop gives you full control over error handling, token tracking, and tool execution security.

Once you build one manually, the magic evaporates and you're left with an inspectable, reliable automation tool.

#python #softwareengineering #ai #automation #developers

_Tags: python, aiagents, openai, coding_

---
*By Suman Giri — built with the CoderFact engine.*