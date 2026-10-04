# Python AI Agents: Build One Tonight Without Heavy Frameworks

_Stop fighting LangChain abstraction layers. Here is how tool-calling actually works under the hood._

## Scroll-stopping hooks

**Hook 1.** Spent three hours last night debugging an agent loop just to realize I didn't need a framework at all.

**Hook 2.** Most tutorials make AI agents sound like rocket science—it is literally just an LLM inside a while loop with a tool registry.

**Hook 3.** Stop installing massive wrapper libraries before you understand raw OpenAI function calling in plain Python.

**Hook 4.** Built a working autonomous agent at 1 AM in under 50 lines of script. The secret? JSON schemas.

**Hook 5.** If your agent is hallucinating its tool inputs, your system prompt isn't the problem—your schema typing is.

## 7 tips that actually move the needle

### Tip 1. Use Pydantic's `model_json_schema()` to generate strict function definitions automatically
_Why it matters:_ Hand-writing JSON schemas for OpenAI tools leads to missing types and runtime parsing errors.

```python
from pydantic import BaseModel
class Query(BaseModel):
    location: str
schema = Query.model_json_schema()
```

### Tip 2. Set `strict=True` inside the tool definition dictionary
_Why it matters:_ This forces models like GPT-4o to strictly adhere to your exact JSON schema without skipping keys.

```
tool = {"type": "function", "function": {"name": "get_weather", "parameters": schema, "strict": True}}
```

### Tip 3. Route tool outputs with a simple dictionary mapping strings to callables
_Why it matters:_ It keeps your execution loop clean without a mess of nested `if/elif` statements.

```
TOOL_MAP = {"get_weather": run_weather, "search_db": run_search}
res = TOOL_MAP[call.name](**json.loads(call.arguments))
```

### Tip 4. Append tool results directly as a message with role 'tool' and the matching 'tool_call_id'
_Why it matters:_ The API throws a 400 error immediately if your response messages don't match the original call ID.

```
messages.append({"role": "tool", "tool_call_id": call.id, "content": str(result)})
```

### Tip 5. Hardcode a maximum loop iteration guard before calling the model
_Why it matters:_ It prevents infinite tool loops that drain your API credits when the model gets stuck.

```
for _ in range(5):
    response = client.chat.completions.create(...)
    if not response.choices[0].message.tool_calls: break
```

### Tip 6. Use `instructor` or `pydantic-ai` when you want typed validation without the bloat
_Why it matters:_ They give you type-safe responses without hiding the HTTP requests behind massive abstractions.

```python
import instructor
client = instructor.from_openai(OpenAI())
```

### Tip 7. Use `rich.console` to inspect every tool call and argument live in terminal
_Why it matters:_ Seeing the raw JSON payloads as they execute saves hours of print-statement debugging.

```python
from rich.console import Console
Console().print(response.choices[0].message.tool_calls)
```

## Step-by-step procedure

### 1. Install the official OpenAI package and python-dotenv
Keep dependencies to a bare minimum so you actually see the execution flow.

```python
pip install openai python-dotenv
```

### 2. Define a plain Python function and its tool schema
Write the actual logic you want the agent to execute, like calculating numbers or checking a file.

```python
def add(a: int, b: int) -> int: return a + b
tools = [{"type": "function", "function": {"name": "add", "parameters": {"type": "object", "properties": {"a": {"type": "int"}, "b": {"type": "int"}}, "required": ["a", "b"]}}]
```

### 3. Initialize the message history with a system prompt and user task
The message list is your agent's working memory throughout the entire lifecycle.

```
messages = [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "What is 42 plus 89?"}]
```

### 4. Create the while loop to handle completions and tool calls
Call the API, check if the model requested a tool, execute the function, and feed the answer back.

```
resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, tools=tools)
msg = resp.choices[0].message
messages.append(msg)
```

### 5. Execute the tool and verify the final answer
Run the script and watch the agent call your function, read the result, and print the finished sentence.

```python
if msg.tool_calls:
    call = msg.tool_calls[0]
    res = add(**json.loads(call.function.arguments))
    messages.append({"role": "tool", "tool_call_id": call.id, "content": str(res)})
    final = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
    print(final.choices[0].message.content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to send the assistant's initial message containing the `tool_calls` back to the API along with the tool result. The OpenAI API requires the assistant message with the tool call to precede the tool response message, or it rejects the request.

## X / Twitter thread (copy-paste ready)

**1/** You don't need a massive framework to build an AI agent in Python. Here is the entire architecture in 5 tweets.

**2/** Spent hours wrestling with bloated agent libraries last night. Stripped it all down to a 40-line script using pure OpenAI tool-calling.

**3/** Tip 1: Define your tools using standard Python dictionaries or Pydantic. Pass them directly to `client.chat.completions.create(..., tools=tools)`.

**4/** Tip 2: Map function names to actual functions in a dictionary like `TOOLS = {'calc': run_calc}`. Run them dynamically using `json.loads(tool_call.arguments)`.

**5/** Tip 3: Always push the tool's return string back into the conversation with role='tool' and the exact `tool_call_id`. Then run one final completion.

**6/** That is literally the entire loop: Prompt -> Model -> Tool Execution -> Append Result -> Final Answer. Try building it from scratch tonight.

## LinkedIn version

At 1:00 AM last night, I caught myself fighting a massive third-party agent framework for two hours straight just trying to get a basic SQL agent to run.

I deleted the entire environment, created a clean virtualenv, and decided to build it using nothing but the official OpenAI Python SDK and a simple `while` loop.

Here is the reality: an AI agent isn't magic. It is an LLM receiving a message history, choosing a function from a list of JSON schemas you provide, waiting for your script to execute that function, and taking the string result back to answer the prompt.

Once you build this loop manually with raw Python dictionaries and functions, you stop dealing with mysterious framework abstractions, broken dependency trees, and weird memory leaks.

If you want to build agentic workflows, skip the heavy wrappers on day one. Write the execution loop yourself first so you actually understand what happens under the hood.

#python #ai #softwareengineering #developers

_Tags: python, aiagents, openai, programming_

---
*By Suman Giri — built with the CoderFact engine.*