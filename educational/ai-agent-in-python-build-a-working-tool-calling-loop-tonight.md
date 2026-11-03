# AI Agent in Python: Build a working tool-calling loop tonight

_Stop overcomplicating agents with heavy frameworks. Here is the raw 30-line loop that actually works._

## Scroll-stopping hooks

**Hook 1.** I spent three hours fighting LangChain abstractions last night just to realize a while-loop and tool calls do the exact same thing.

**Hook 2.** Most framework-based AI agents are just 200 lines of setup wrapping a basic function call — let's build the raw core instead.

**Hook 3.** If you know how to write a Python dictionary and a while loop, you already know how to build a fully functional AI agent.

**Hook 4.** Stop importing massive agent frameworks before you understand the tool-use loop that powers them under the hood.

**Hook 5.** I finally scrapped my bloated agent setup at 1am and rewrote it in 30 lines of standard Python. It runs faster and breaks less.

## 7 tips that actually move the needle

### Tip 1. Use litellm instead of official SDKs to prevent vendor lock-in
_Why it matters:_ It normalizes tool-calling schemas across OpenAI, Anthropic, and local Ollama models with zero code changes.

```python
from litellm import completion
resp = completion(model='gpt-4o', messages=msgs, tools=tools)
```

### Tip 2. Define tools using plain Pydantic models and docstrings
_Why it matters:_ The model uses your parameter type hints and docstrings to decide when and how to call your function.

```python
def get_weather(location: str) -> str:
    """Fetch weather for a given city."""
    return f'Sunny in {location}'
```

### Tip 3. Enforce strict JSON response parsing with pydantic-core
_Why it matters:_ Model outputs drift over long conversations, so validating payload schemas early saves runtime crashes.

```python
from pydantic import BaseModel
class Action(BaseModel):
    tool_name: str
    arguments: dict
```

### Tip 4. Store conversation state in a simple list of dicts
_Why it matters:_ Passing explicit `user`, `assistant`, and `tool` role objects keeps the state deterministic and easy to debug.

```
messages = [{'role': 'user', 'content': 'Check Kolkata weather'}]
```

### Tip 5. Execute tool calls dynamically using a Python dictionary mapping
_Why it matters:_ It avoids messy `if/else` chains and lets you register new agent capabilities cleanly.

```
TOOL_MAP = {'get_weather': get_weather}
result = TOOL_MAP[tool_name](**args)
```

### Tip 6. Set hard limits on execution loop iterations
_Why it matters:_ Unchecked agent loops can get stuck calling the same broken tool until your API quota burns out.

```
MAX_TURNS = 5
for _ in range(MAX_TURNS): pass
```

### Tip 7. Log raw LLM tool-call payloads to a local JSON line file
_Why it matters:_ Inspecting exact model inputs at 1am is much easier when you have plain text files to grep through.

```
with open('agent.log', 'a') as f:
    f.write(json.dumps(response) + '\n')
```

## Step-by-step procedure

### 1. Install core dependencies
Grab litellm to talk to LLMs and standard library imports to handle execution.

```python
pip install litellm pydantic
```

### 2. Define a Python function with clear docstrings
Write the actual tool your agent will execute when it needs outside data.

```python
def fetch_coderfact_status(service: str) -> str:
    """Checks health status of a CoderFact service."""
    return f'{service} is operational'
```

### 3. Build the JSON Schema for the tool
Format your tool definition so the model knows what arguments it requires.

```
tools = [{
    'type': 'function',
    'function': {
        'name': 'fetch_coderfact_status',
        'description': 'Checks health status of a CoderFact service.',
        'parameters': {
            'type': 'object',
            'properties': {'service': {'type': 'string'}},
            'required': ['service']
        }
    }
}]
```

### 4. Construct the main execution loop
Send messages to the model, inspect if it wants to call a tool, execute the function, and append the result back to state.

```
messages = [{'role': 'user', 'content': 'Is the api service up on CoderFact?'}]
response = completion(model='gpt-4o', messages=messages, tools=tools)
msg = response.choices[0].message
if msg.tool_calls:
    tool_call = msg.tool_calls[0]
    # handle execution
```

### 5. Append execution output and request final answer
Feed the tool's return string back into the conversation list with the `tool` role so the agent can digest it.

```
messages.append(msg)
messages.append({
    'role': 'tool',
    'tool_call_id': tool_call.id,
    'content': 'api is operational'
})
final_resp = completion(model='gpt-4o', messages=messages)
```

### 6. Run the agent and print the verified response
Execute your script to verify the agent successfully called your function and summarized the result.

```python
print(final_resp.choices[0].message.content)
# Output: The API service on CoderFact is currently operational.
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the assistant's initial response (containing `tool_calls`) back to the messages array before sending the tool output. The fix: always push `response.choices[0].message` into your message history array right before adding the role='tool' response, or OpenAI/Anthropic APIs will reject your follow-up request with an invalid sequence error.

## X / Twitter thread (copy-paste ready)

**1/** You don't need heavy frameworks to build an AI agent — just a while loop and tool calls.

**2/** Last night I scrapped a bloated framework setup for a clean Python script. It ran faster and actually worked.

**3/** Tip 1: Use litellm to abstract provider APIs so you can swap OpenAI, Anthropic, or Ollama without rewriting code.

**4/** Tip 2: Map your local functions in a simple dictionary `{'name': fn}` so your agent can execute them dynamically.

**5/** Tip 3: Always set a strict iteration cap (`MAX_TURNS = 5`) on your execution loop so bad model responses don't drain your API credits.

**6/** Build the raw loop first before reaching for complex abstractions. Full code guide dropping on CoderFact.

## LinkedIn version

I spent half of last night fighting framework abstractions just to get a simple task execution agent working.

Every time I wanted to debug a tool call, I had to trace through five layers of class wrappers, hidden async managers, and obscure configuration objects. At 1am, I finally deleted the library and rewrote the entire thing in raw Python.

Turns out, a functional AI agent is ridiculously simple: it's just a loop. You send messages to an LLM, inspect if the response asks for a function call, run that function locally, append the output to your message array, and send it right back.

When you strip away the hype, tool-calling boils down to clear docstrings, solid type hints, and basic dict mappings. If you build this raw core once, you'll actually understand what your agentic workflows are doing under the hood instead of guessing why a 300-line framework call hung silently.

Start small: write the raw loop first, verify your state updates, and add abstractions only when your codebase explicitly asks for them.

#python #aiagents #backend #softwareengineering #coding

_Tags: python, aiagents, automation, llm_

---
*By Suman Giri — built with the CoderFact engine.*