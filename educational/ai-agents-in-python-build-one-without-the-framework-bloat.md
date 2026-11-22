# AI Agents in Python: Build One Without the Framework Bloat

_Stop fighting heavy agent frameworks. Write a 30-line while-loop with function calling instead._

## Scroll-stopping hooks

**Hook 1.** Frameworks try to sell you 500-line abstractions for what is fundamentally just a while-loop and a tool schema.

**Hook 2.** Spent 3 hours debugging a LangChain memory leak last night before realizing I could just append JSON to a list.

**Hook 3.** Your first AI agent shouldn't require a 40MB dependency graph just to check the weather.

**Hook 4.** An AI agent isn't magic—it's an LLM in a loop that outputs structured JSON until it decides to stop.

**Hook 5.** I stripped away every agent library and built a working Python agent from scratch at 1am. It took 35 lines.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to auto-generate tool schemas instead of writing raw JSON definitions by hand.
_Why it matters:_ It keeps your code typed, validated, and cuts out 50 lines of boilerplate error handling.

```python
from pydantic import BaseModel
class Calculate(BaseModel):
    expression: str
```

### Tip 2. Set temperature=0.0 when testing tool selection.
_Why it matters:_ Flaky temperature settings ruin determinism when you're trying to debug tool routing logic.

```
response = client.chat.completions.create(model='gpt-4o', temperature=0.0, messages=messages)
```

### Tip 3. Store tool handlers in a simple Python dictionary mapping string names to functions.
_Why it matters:_ It eliminates gross `if-elif` chains and lets you dispatch tool calls dynamically.

```
TOOL_MAP = {'search': run_search, 'calc': run_calc}
result = TOOL_MAP[call.name](**call.args)
```

### Tip 4. Inspect raw API responses using tenacity to retry failed tool parsing automatically.
_Why it matters:_ LLMs occasionally mess up schema formatting, and retrying beats crashing the entire loop.

```python
@retry(stop=stop_after_attempt(3))
def call_llm(msgs): return client.chat.completions.create(...)
```

### Tip 5. Append tool execution outputs back to the message history with role 'tool'.
_Why it matters:_ The LLM needs context on what happened after it invoked a function to produce the next response.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(output)})
```

### Tip 6. Set a hard ceiling on your execution loop iterations.
_Why it matters:_ Without a maximum step count, a confused agent will burn through your API credits in an infinite loop.

```
for _ in range(max_steps:=5):
    if not response.tool_calls: break
```

### Tip 7. Log raw LLM payload inputs and outputs to a local file during local dev.
_Why it matters:_ Tracing agents without UI frameworks is trivial if you just dump the message stack to disk.

```python
import json; open('agent.log', 'a').write(json.dumps(messages, indent=2))
```

## Step-by-step procedure

### 1. Install official SDKs and setup environment
Skip the wrapper packages. Grab the official OpenAI SDK and python-dotenv for API key management.

```python
pip install openai python-dotenv
```

### 2. Define a Python function and its tool schema
Write the actual local function you want the model to execute, then define the schema telling the model how to call it.

```python
def get_user_stats(user_id: str) -> str:
    return f"User {user_id}: Active"

tools = [{'type': 'function', 'function': {'name': 'get_user_stats', 'parameters': {'type': 'object', 'properties': {'user_id': {'type': 'string'}}}}}]
```

### 3. Initialize the conversation message stack
Create a list containing your system prompt and initial user input—this list acts as the agent's working memory.

```
messages = [
    {'role': 'system', 'content': 'Use tools when needed.'},
    {'role': 'user', 'content': 'Check status for user_123'}
]
```

### 4. Build the evaluation while-loop
Send messages to the model, check if it wants to invoke a tool, execute the function if called, and feed the output back in.

```
while True:
    res = client.chat.completions.create(model='gpt-4o', messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls: break
    for call in msg.tool_calls:
        # Tool execution happens here
        pass
```

### 5. Map and dispatch function calls dynamically
Parse the returned tool call, run the actual Python function, and append the result to history.

```
tool_output = get_user_stats(**json.loads(call.function.arguments))
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': tool_output})
```

### 6. Verify end-to-end agent execution output
Run your script and observe the final string response. It should process the tool output and give a clear human answer.

```python
print(messages[-1]['content'])
# Output: 'User user_123 is currently active.'
```

## The mistake almost everyone makes

> ⚠️  Passing raw tool execution error traces straight back into the message stack. When a tool throws an unhandled exception, your agent loop crashes completely—wrap tool calls in a try-except block and feed the stringified error message back as the tool output so the LLM can self-correct.

## X / Twitter thread (copy-paste ready)

**1/** Building your first AI agent in Python doesn't require complex frameworks. Here is how it actually works under the hood 🧵

**2/** At its core, an AI agent is just an LLM in a loop with permission to call functions. That's it. No magic abstractions needed.

**3/** Step 1: Define normal Python functions for actions you want to allow (fetching data, DB queries, API calls).

**4/** Step 2: Pass function schemas to the model. Using pure `openai` package + simple Python dicts keeps things predictable.

**5/** Step 3: Run a while-loop. If the model returns a tool call, run the code, append the output to message history, and repeat.

**6/** Stop importing heavy frameworks until you actually outgrow a 30-line script. Code details above!

## LinkedIn version

I spent half of last night fighting heavy framework abstractions just to get a simple AI workflow running. Every simple task felt buried under five layers of wrappers, custom classes, and hidden prompts.

So at 1am, I threw out the dependencies, opened a clean file, and wrote a Python agent using pure standard library structures and the native OpenAI client. It took under 40 lines of clear, readable code.

Stripping away the noise makes you realize what an agent actually is—it is just an LLM sitting in an execution loop. You send a message history, the model decides if it needs an external tool, you run that tool on your machine, feed the response back in, and repeat until it finishes.

Building this raw pattern first gives you complete control over debugging, retries, and costs. You can log exact payloads without wading through third-party stack traces when something breaks.

Before pulling in massive agent orchestration libraries for your next side project, try writing the while-loop yourself once. It makes everything much easier to reason about.

#python #ai #backend #softwareengineering

_Tags: python, aiagents, openai, backend_

---
*By Suman Giri — built with the CoderFact engine.*