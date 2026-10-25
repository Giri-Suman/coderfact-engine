# AI Agents in Python: Build One Tonight Without LangChain Bloat

_Stop overcomplicating agents with massive frameworks. A simple while loop and function calling is all you need._

## Scroll-stopping hooks

**Hook 1.** Most AI agent tutorials drown you in 12 layers of framework abstractions before making a single API call. You can write an actual working agent in 40 lines of raw Python.

**Hook 2.** Spent until 1:30 AM debugging an agent framework issue only to realize an 'agent' is literally just an LLM sitting inside a while loop. Here is the bare minimum setup that actually works.

**Hook 3.** You do not need LangChain, CrewAI, or an enterprise orchestration platform to build an AI agent that executes real code. Raw OpenAI function calling plus standard library is faster to debug.

**Hook 4.** If your AI agent keeps hallucinating answers instead of using tools, stop tweaking your system prompt. Your function signatures are missing strict parameter schemas.

**Hook 5.** The biggest scam in modern AI tooling is convincing developers they need a 400MB dependency tree to write a script that searches a directory and runs a tool.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to auto-generate strict OpenAI tool schemas instead of writing raw JSON
_Why it matters:_ Hand-rolled JSON schemas inevitably miss edge-case types and break tool routing.

```python
from pydantic import BaseModel, Field
class WeatherQuery(BaseModel):
    city: str = Field(description='City name to search')
```

### Tip 2. Set tool_choice='auto' in client.chat.completions.create to let the LLM decide when to call tools
_Why it matters:_ Forcing tools manually defeats the point of an autonomous agent loop.

```
res = client.chat.completions.create(
    model='gpt-4o-mini', messages=msgs, tools=tools, tool_choice='auto'
)
```

### Tip 3. Map function names directly to Python callables using a simple dictionary lookup
_Why it matters:_ Avoid dangerous eval() patterns and keep your execution surface safe.

```
TOOL_MAP = {'fetch_weather': fetch_weather, 'run_sql': run_sql}
result = TOOL_MAP[tool_call.function.name](**json.loads(tool_call.function.arguments))
```

### Tip 4. Append the tool execution result back to the messages list with role='tool' and matching tool_call_id
_Why it matters:_ The LLM will crash or lose conversation state if the tool call ID is omitted.

```
msgs.append({
    'role': 'tool', 'tool_call_id': call.id, 'content': str(result)
})
```

### Tip 5. Wrap the tool dispatch inside a while loop with a strict max_iterations guard
_Why it matters:_ Runaway loops will silently drain your API credits if the agent gets trapped in a cycle.

```
for _ in range(MAX_STEPS):
    if not response.choices[0].message.tool_calls: break
```

### Tip 6. Use instructor library if you want typed structured outputs directly from local tools
_Why it matters:_ It validates incoming tool arguments before your actual Python logic touches them.

```python
import instructor, openai
client = instructor.from_openai(openai.OpenAI())
```

### Tip 7. Log raw LLM responses with rich.pretty before parsing tool calls during local dev
_Why it matters:_ Seeing malformed arguments directly in the terminal saves hours of mysterious traceback digging.

```python
from rich import print
print(response.choices[0].message.tool_calls)
```

## Step-by-step procedure

### 1. Install the official OpenAI SDK and Python dotenv
Keep your environment clean — you do not need 30 transitive dependencies just to invoke a model with functions.

```python
pip install openai python-dotenv
```

### 2. Define a plain Python function and its OpenAI tool schema
Write the function that performs the real task, then describe it in a format the model understands.

```python
def get_system_load():
    import os
    return str(os.getloadavg())

tools = [{'type': 'function', 'function': {'name': 'get_system_load', 'description': 'Returns system CPU load average'}}]
```

### 3. Initialize message history with a direct system instruction
Tell the model what tools it has access to and explicitly instruct it to answer using data from tool calls.

```
messages = [{'role': 'system', 'content': 'You are a dev assistant. Use provided tools when requested.'}, {'role': 'user', 'content': 'What is the current server load?'}]
```

### 4. Build the execution loop that handles tool calls
Call the API, check if the response requests a tool call, run the mapped function, and append the result.

```
resp = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tools)
call = resp.choices[0].message.tool_calls[0]
res = get_system_load()
messages.extend([resp.choices[0].message, {'role': 'tool', 'tool_call_id': call.id, 'content': res}])
```

### 5. Send the updated history back to get the final synthesis
Make the second API call so the model reads the tool output and gives you the final user-facing string.

```python
final_resp = client.chat.completions.create(model='gpt-4o-mini', messages=messages)
print(final_resp.choices[0].message.content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to feed the model's intermediate assistant response containing tool_calls back into the message history before sending the tool result. The API rejects orphaned tool messages; you must append the assistant message, then the tool message, then call the model again.

## X / Twitter thread (copy-paste ready)

**1/** You do not need massive agent frameworks to build a working AI assistant in Python. (1/6)

**2/** An AI agent is basically an LLM running inside a while loop with access to a function dispatcher. That is the entire architecture. (2/6)

**3/** Step 1: Write a normal Python function. Step 2: Write a JSON description of it. Feed both to OpenAI client.chat.completions with tools=[...]. (3/6)

**4/** When response.choices[0].message.tool_calls is populated, execute your local Python function using a clean dictionary lookup. Skip eval(). (4/6)

**5/** Always append both the assistant's tool-call message AND your tool output message back to the conversation array before calling the API again. (5/6)

**6/** Build it yourself once with 40 lines of standard Python before reaching for bloated orchestrators. What tools are you hooking up first? (6/6)

## LinkedIn version

It was 1:00 AM, my terminal was spitting out mysterious recursion errors, and my Python virtual environment was bloated with 400MB of agent framework dependencies. All I wanted was a script that checked server logs, ran a quick diagnostic command, and summarized the issue.

After tearing out the framework completely, I went back to first principles. Turns out, an AI agent is not some arcane architectural puzzle. It is just an LLM inside a while loop that knows how to output JSON when it wants your code to run a task.

Here is the entire mental model: you define a standard Python function, pass its parameter description to the model, check if the response asks for a tool call, run the function locally, and post the output back to the conversation. That is the whole trick.

Once you build this loop with raw Python and OpenAI function calling, you realize how much unnecessary complexity gets pushed on developers. No weird memory abstractions, no hidden prompt templates, no magical chains that break the moment you need custom logging.

If you want to understand agents, write one from scratch tonight with zero third-party orchestrators. You will learn more in 30 minutes of vanilla Python than in a week of fighting framework docs.

#python #automation #softwareengineering #developer #ai

_Tags: python, automation, aiagents, devtips_

---
*By Suman Giri — built with the CoderFact engine.*