# AI agents in Python: build one from scratch without a framework

_Stop overcomplicating agents with 50 abstractions. It is literally just a while loop and tool calls._

## Scroll-stopping hooks

**Hook 1.** I spent three hours debugging a framework's agent abstractions last night before realizing the whole thing is just a while loop checking for tool calls.

**Hook 2.** You don't need a massive framework to build an AI agent—just raw Python, an API client, and a basic loop.

**Hook 3.** Most agent tutorials sell you complex orchestration libraries when 40 lines of clean Python will do the exact same job.

**Hook 4.** If your AI agent breaks every time a dependency updates, you built the library's agent, not your own.

**Hook 5.** Building an AI agent boils down to one pattern: prompt the model, catch the function call, run it locally, send the output back.

## 7 tips that actually move the needle

### Tip 1. Use the official `openai` SDK directly instead of high-level wrapper libraries
_Why it matters:_ It keeps your mental model clear and prevents hidden abstraction bugs when tool definitions change.

```python
from openai import OpenAI
client = OpenAI()
```

### Tip 2. Define your tools using standard JSON schema in the `tools` parameter
_Why it matters:_ It forces the LLM to return strictly structured arguments instead of unpredictable free text.

```
tools = [{'type': 'function', 'function': {'name': 'get_weather', 'parameters': {...}}}]
```

### Tip 3. Run a simple `while response.choices[0].finish_reason == 'tool_calls'` loop
_Why it matters:_ This creates an autonomous execution cycle where the agent keeps running tools until it decides it has the answer.

```
while choice.finish_reason == 'tool_calls':
    # execute tool and append to message history
```

### Tip 4. Map function names directly to Python functions using a dictionary lookup
_Why it matters:_ Avoids messy `if/else` chains when executing tools returned by the API.

```
TOOL_MAP = {'get_weather': get_weather}
output = TOOL_MAP[tool_call.function.name](**args)
```

### Tip 5. Append tool outputs back to the conversation stack with `role: 'tool'`
_Why it matters:_ The LLM needs the returned data contextually linked to its specific call ID to continue reasoning.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(result)})
```

### Tip 6. Cap the loop execution count with an `iteration_limit` safety guard
_Why it matters:_ Prevents infinite loops and drained API credits if the model gets stuck calling tools endlessly.

```
if iterations > 5: raise TimeoutError('Agent loop limit reached')
```

### Tip 7. Print every message turn with `rich` or plain color logs while building
_Why it matters:_ Seeing the raw system message, tool call request, and tool output in real time makes debugging trivial.

```python
print(f'[TOOL CALL] {call.function.name} args={call.function.arguments}')
```

## Step-by-step procedure

### 1. Initialize your project and install the API client
Set up a lightweight Python script and install the minimal client library.

```python
pip install openai
```

### 2. Define a concrete Python function for the agent to call
Write a normal local function that does real work, like fetching system info or hitting an API.

```python
def calculate_tax(amount: float) -> str:
    return str(amount * 0.18)
```

### 3. Construct the OpenAI tool specification schema
Tell the model what your function is named, what it does, and what arguments it expects.

```
tools = [{'type': 'function', 'function': {'name': 'calculate_tax', 'description': 'Calculates tax', 'parameters': {'type': 'object', 'properties': {'amount': {'type': 'number'}}, 'required': ['amount']}}}]
```

### 4. Build the execution loop
Send the conversation history to the model, inspect the response, and execute the requested tool if present.

```
messages = [{'role': 'user', 'content': 'What is the tax on $250?'}]
res = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tools)
# append res and run tool
```

### 5. Pass tool execution results back to the model for final synthesis
Push the execution output back into the message array and call the API again to get a final natural language answer.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': result})
final_res = client.chat.completions.create(model='gpt-4o-mini', messages=messages)
```

### 6. Run the complete script and verify the output
Execute your script—you should see the agent intercept your prompt, call the local Python function, and return the correct calculated result.

```
python agent.py
# Output: The tax on $250 is $45.0.
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the assistant's original message containing the tool call request before appending the tool result. The API will crash with a missing tool call error—always append the assistant response first, then the tool output.

## X / Twitter thread (copy-paste ready)

**1/** Building your first AI agent in Python doesn't require a 50k-star framework.

**2/** At its core, an agent is just an LLM sitting inside a while loop with access to execution functions.

**3/** First, write your local Python tools. Just standard functions that perform action scripts or API calls.

**4/** Pass those tool definitions as JSON schemas into your API completion call so the model knows they exist.

**5/** Check if the model returned a tool call request. If it did, run your local function with the provided arguments and push the result back into the chat history.

**6/** That's literally the whole loop. Stop overcomplicating your stack—build it raw first, then pull in frameworks if you actually need them.

## LinkedIn version

I spent half of last night wrestling with an agent framework's abstract routing system just to run a basic SQL tool call. At 1am, I scrapped the library, opened a clean file, and wrote it in plain Python.

Turns out an AI agent isn't magic—it's just a while loop and function calls.

You pass your system prompt and local tool schemas to the model API. If the model decides it needs data, it pauses generation and asks you to execute a specific function with generated arguments. You execute it in Python, hand the output back to the model, and repeat.

Once you build this pattern manually once, the mental fog around 'agents' completely disappears. You realize you don't need five layers of third-party wrappers to build useful automation.

If you're getting started with AI tooling, skip the massive frameworks for your first prototype. Write the loop yourself—it takes under 50 lines of code and actually makes sense when something goes wrong.

ai python softwareengineering webdevelopment programming

_Tags: python, aiagents, openai, automation_

---
*By Suman Giri — built with the CoderFact engine.*