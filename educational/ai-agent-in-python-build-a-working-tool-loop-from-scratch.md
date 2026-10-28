# AI agent in Python: Build a working tool loop from scratch

_Stop paying for fancy orchestration frameworks when a 40-line while loop and function calling does the job._

## Scroll-stopping hooks

**Hook 1.** Most 'AI agent' frameworks are just 10,000 lines of abstraction hiding a basic while-loop and an API call.

**Hook 2.** I spent three hours debugging a LangChain agent before throwing it out and writing 35 lines of pure Python.

**Hook 3.** Your LLM doesn't need a framework to use tools—it just needs a JSON schema and a python execute function.

**Hook 4.** If you can write a `while True` loop and parse a dictionary, you can build a fully functional AI agent tonight.

**Hook 5.** Stop importing massive agent libraries until you've built one using raw `openai` and standard Python functions.

## 7 tips that actually move the needle

### Tip 1. Use type hints and docstrings on standard Python functions to auto-generate tool schemas.
_Why it matters:_ It keeps your code DRY so you don't have to manually write massive JSON schemas for every tool.

```python
def get_weather(location: str) -> str:
    """Fetch current weather for a city."""
    return f"22C in {location}"
```

### Tip 2. Bind tools directly using `client.chat.completions.create(..., tools=tools)` in the official OpenAI SDK.
_Why it matters:_ Native function calling is much more reliable than trying to prompt-engineer an LLM to output structured JSON manually.

```
response = client.chat.completions.create(
    model="gpt-4o-mini", messages=messages, tools=my_tools
)
```

### Tip 3. Enforce a strict loop counter limit (`max_iters = 5`) inside your agent's execution loop.
_Why it matters:_ It prevents runaway recursive tool calls from burning through your API credits at 1 AM.

```
for _ in range(5):
    if not response.choices[0].message.tool_calls: break
```

### Tip 4. Append tool responses back to the original `messages` array with `role: 'tool'` and the matching `tool_call_id`.
_Why it matters:_ The LLM loses context instantly if tool response messages aren't matched back to its initial function call ID.

```
messages.append({"role": "tool", "tool_call_id": call.id, "content": str(result)})
```

### Tip 5. Wrap tool execution logic in a `try/except` block and pass the stringified error stack back to the model.
_Why it matters:_ LLMs can self-correct their input arguments if you give them the actual Python error message.

```
except Exception as e:
    messages.append({"role": "tool", "tool_call_id": call.id, "content": f"Error: {e}"})
```

### Tip 6. Log raw LLM responses to a local file using `rich.print` or standard `logging` during tool calls.
_Why it matters:_ You need to see the exact payload sent when the model decides to invoke a function versus outputting final text.

```python
from rich import print
print(response.choices[0].message.tool_calls)
```

### Tip 7. Use Pydantic's `type2json` or `pydantic.TypeAdapter` to validate raw tool arguments before invoking them.
_Why it matters:_ It catches missing or misformatted arguments before your actual tool functions crash.

```
args = my_pydantic_model.model_validate_json(call.function.arguments)
```

## Step-by-step procedure

### 1. Step 1: Install the OpenAI Python SDK
Set up a clean virtual environment and install the latest OpenAI package along with dotenv.

```python
pip install openai python-dotenv
```

### 2. Step 2: Define your python tool functions
Write simple functions for the actions you want your agent to perform, like checking system stats or fetching local data.

```python
def calculate_tax(amount: float) -> str:
    return str(amount * 0.18)
```

### 3. Step 3: Define the tool schemas for the API
Map your Python functions into the standard OpenAI tools JSON structure so the model knows they exist.

```
tools = [{
    "type": "function",
    "function": {
        "name": "calculate_tax",
        "description": "Calculate 18% tax on an amount",
        "parameters": {
            "type": "object",
            "properties": {"amount": {"type": "number"}},
            "required": ["amount"]
        }
    }
}]
```

### 4. Step 4: Build the execution registry
Map function names to actual executable functions in a standard Python dictionary for instant lookup.

```
available_tools = {"calculate_tax": calculate_tax}
```

### 5. Step 5: Implement the main agent while-loop
Create a loop that passes messages to the LLM, executes returned tool calls, feeds results back, and breaks when the model yields a final text answer.

```
messages = [{"role": "user", "content": "What is the tax on 250?"}]
while True:
    res = client.chat.completions.create(model="gpt-4o-mini", messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls: break
    for call in msg.tool_calls:
        fn = available_tools[call.function.name]
        args = json.loads(call.function.arguments)
        out = fn(**args)
        messages.append({"role": "tool", "tool_call_id": call.id, "content": out})
```

### 6. Step 6: Run and verify the complete flow
Print the final message from the conversation history to confirm the model accurately used the tool output to answer your prompt.

```python
print(messages[-1].content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the assistant's message (`msg`) to the `messages` list *before* appending tool response messages. The API will throw an invalid request error because a tool response must directly follow an assistant message containing tool calls.

## X / Twitter thread (copy-paste ready)

**1/** You don't need heavy frameworks to build AI agents. You just need a while loop.

**2/** Most agent abstractions hide what's actually happening: prompt -> tool_call -> run_function -> loop.

**3/** Step 1: Write raw Python functions for your tools and map them into a simple execution dictionary.

**4/** Step 2: Pass your tools array into `client.chat.completions.create()` using native function calling.

**5/** Step 3: Loop over `message.tool_calls`, run your local code, and append the output with `role: 'tool'`.

**6/** Build it raw first so you actually understand agent loops. Full guide drop coming on CoderFact.

## LinkedIn version

I spent half of last night trying to get a third-party framework agent to stop crashing on simple tool calls. After reading through endless stack traces, I deleted the package and decided to write it from scratch using plain Python.

It turns out a functional AI agent is just a while loop, a function registry dictionary, and OpenAI's native tool-calling interface. That's literally it.

When the model decides it needs external data, it returns a `tool_calls` payload instead of text. You run that local function, return the result back to the message list with a `role: 'tool'`, and pass the conversation history right back to the model.

Building this raw cleared up all the mystery. No hidden abstractions, no bizarre parsing errors, and complete control over credit usage and execution logic.

If you haven't built an agent loop without libraries yet, do it tonight—it takes under 50 lines of code.

#python #aiengineering #softwareengineering #backend

_Tags: python, aiagents, openai, automation_

---
*By Suman Giri — built with the CoderFact engine.*