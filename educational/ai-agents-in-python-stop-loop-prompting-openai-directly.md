# AI Agents in Python: Stop Loop-Prompting OpenAI Directly

_Build a zero-dependency Python agent that actually uses tools in under 50 lines of code._

## Scroll-stopping hooks

**Hook 1.** I stayed up till 2 AM trying to get an LLM to reliably call my own Python functions without breaking JSON schemas.

**Hook 2.** Most 'AI Agent' tutorials force a massive framework on you before you even understand what a loop looks like.

**Hook 3.** If your AI agent is just a system prompt wrapped in a while-loop, you're one API timeout away from an infinite bill.

**Hook 4.** You don't need LangChain or LlamaIndex to build a functional tool-calling agent in Python.

**Hook 5.** I finally built a working Python agent from scratch last night after realizing function calling is just a structured while-loop.

## 7 tips that actually move the needle

### Tip 1. Use raw pydantic models to define agent tool schemas instead of manual JSON writing
_Why it matters:_ It prevents the LLM from passing malformed arguments that crash your runtime execution.

```
class WeatherInput(BaseModel):
    location: str = Field(description='City name')
```

### Tip 2. Enforce a maximum turn limit inside your execution while-loop
_Why it matters:_ LLMs can get stuck in repeating tool-call loops when they get confused by an error message.

```
for _ in range(max_turns):
    response = client.chat.completions.create(...)
```

### Tip 3. Pass execution errors back to the model as role='tool' messages
_Why it matters:_ It gives the LLM a chance to self-correct its arguments rather than throwing an unhandled Python exception.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': f'Error: {str(e)}'})
```

### Tip 4. Bind native Python functions to names using a simple dispatch dictionary
_Why it matters:_ It decouples string names returned by the model from your actual code execution logic.

```
TOOL_MAP = {'get_weather': fetch_weather, 'run_sql': query_db}
```

### Tip 5. Use low temperature (0.0 to 0.2) specifically for tool-calling turns
_Why it matters:_ Higher creativity causes the model to invent non-existent arguments or hallucinate tool names.

```
client.chat.completions.create(model='gpt-4o-mini', temperature=0.0)
```

### Tip 6. Inspect the raw response object tool_calls attribute before parsing content
_Why it matters:_ When an LLM chooses to call a tool, the content field is often empty or None.

```
if response.choices[0].message.tool_calls:
    handle_tools()
```

### Tip 7. Log full message histories with rich or icecream during local debugging
_Why it matters:_ Seeing the exact sequence of system, assistant, and tool messages is the only way to debug agent logic.

```python
from icecream import ic
ic(messages)
```

## Step-by-step procedure

### 1. Define your Python functions and schemas
Write standard Python functions and create their corresponding JSON schemas so the model knows what arguments to pass.

```python
def add(a: int, b: int) -> int:
    return a + b

tools = [{'type': 'function', 'function': {'name': 'add', 'parameters': {'type': 'object', 'properties': {'a': {'type': 'integer'}, 'b': {'type': 'integer'}}, 'required': ['a', 'b']}}}]
```

### 2. Initialize message history with system instructions
Set up a standard list of dictionaries to track the ongoing conversation context.

```
messages = [{'role': 'system', 'content': 'You are a helpful assistant. Use tools when needed.'}, {'role': 'user', 'content': 'What is 42 + 58?'}]
```

### 3. Set up the execution loop
Create a bounded loop that repeatedly calls the API until the model returns a final text answer.

```python
from openai import OpenAI
client = OpenAI()

for _ in range(5):
    res = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls:
        break
```

### 4. Parse and execute tool calls
Iterate over requested tool calls, map the string name to your local function, and parse stringified JSON arguments.

```python
import json

if msg.tool_calls:
    for call in msg.tool_calls:
        args = json.loads(call.function.arguments)
        result = add(**args)
        messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(result)})
```

### 5. Run final evaluation turn
Execute the script and confirm the model processes the tool output to return a plain text answer.

```python
final_res = client.chat.completions.create(model='gpt-4o-mini', messages=messages)
print(final_res.choices[0].message.content)
# Output: The sum of 42 and 58 is 100.
```

## The mistake almost everyone makes

> ⚠️  Appending tool outputs as standard user messages instead of tool role messages with matching tool_call_id. The API will return a 400 validation error if the assistant's tool call isn't directly followed by a tool role message containing that exact call ID.

## X / Twitter thread (copy-paste ready)

**1/** You don't need a heavy framework to build an AI agent in Python. (1/6)

**2/** Spent hours wrestling with abstractions yesterday before realizing raw function calling is just a 20-line loop. (2/6)

**3/** Tip 1: Always bound your agent loop with a max turn count (e.g., max 5 iterations) to avoid burning credits on endless loops. (3/6)

**4/** Tip 2: Wrap function arguments in standard json.loads calls and handle execution exceptions inside the loop. (4/6)

**5/** Tip 3: Feed runtime errors back to the model using role='tool' so it can fix its own bad inputs. (5/6)

**6/** I put together a zero-dependency script for this on CoderFact. Stop over-engineering your basic agents. (6/6)

## LinkedIn version

I stayed up past 1 AM trying to get a basic AI agent working for a small tool I'm building at CoderFact.

I started out doing what everyone tells you to do: pulling in massive orchestration frameworks. Two hours later, I was buried in custom abstractions, broken tracebacks, and zero clear visibility into why the model kept hallucinating function arguments.

So I threw out the dependencies and built it from scratch in raw Python.

Turns out, an AI agent isn't magic. It's literally just a while-loop. You pass a list of messages and function schemas to an LLM, check if it wants to invoke a tool, run that local function in Python, and feed the string result back into the message array under a 'tool' role.

Once you build it yourself with pure OpenAI SDK calls, you realize how much bloat you were carrying. You get absolute control over your retry logic, error handling, and message history optimization without mysterious framework abstractions getting in the way.

python ai automation backend

_Tags: python, aiagents, openai, webdev_

---
*By Suman Giri — built with the CoderFact engine.*