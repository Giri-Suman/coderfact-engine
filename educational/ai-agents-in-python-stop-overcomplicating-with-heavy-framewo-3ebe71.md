# AI agents in Python: Stop overcomplicating with heavy frameworks

_How to build a useful AI agent in 50 lines of raw Python without LangChain or crewAI bloat._

## Scroll-stopping hooks

**Hook 1.** Spent until 2 AM trying to get a basic AI agent to stop looping infinitely in LangChain. Stripped it all out, wrote 40 lines of vanilla Python, and it worked instantly.

**Hook 2.** You don't need a massive framework to build an AI agent. Most of them are just overpriced wrappers around a basic while loop and a system prompt.

**Hook 3.** I stayed up way too late debugging a state manager in an agent library just to realize a simple Python dictionary did the exact same thing in one line.

**Hook 4.** If your AI agent needs 5 external dependencies just to search Google and summarize a page, you're doing it wrong. Let's build one with zero bloat.

**Hook 5.** The secret to AI agents isn't complex architecture—it's just giving an LLM a list of functions it can call and parsing the JSON output.

## 7 tips that actually move the needle

### Tip 1. Use pydantic for structured outputs instead of raw string parsing
_Why it matters:_ It forces the LLM to return valid JSON that maps directly to your Python classes without manual regex parsing.

```
class ToolCall(BaseModel):
    name: str
    args: dict
```

### Tip 2. Bind tools directly to the OpenAI client using the tools parameter
_Why it matters:_ It offloads the function-calling schema validation to the API level rather than writing custom parsing logic.

```
client.chat.completions.create(model='gpt-4o', messages=msgs, tools=my_tools)
```

### Tip 3. Use the instructor library to patch your LLM client
_Why it matters:_ It makes validating complex nested agent responses incredibly simple without writing custom validation loops.

```python
import instructor; client = instructor.from_openai(OpenAI())
```

### Tip 4. Limit your agent's execution loop with a hard max_iterations counter
_Why it matters:_ It prevents runaway API costs when the agent gets stuck in an infinite tool-calling loop.

```
for _ in range(max_iterations):
    # run agent step
```

### Tip 5. Use rich for terminal logging during development
_Why it matters:_ You need to see exactly when the agent transitions from thinking to tool execution without drowning in raw JSON logs.

```python
from rich.console import Console; console = Console()
```

### Tip 6. Store agent memory in a simple list of dictionaries
_Why it matters:_ Appending messages to a list is lightweight and keeps the entire conversation context intact for the next loop.

```
messages.append({'role': 'user', 'content': prompt})
```

### Tip 7. Use duckduckgo-search for instant web access tools
_Why it matters:_ It requires zero API keys and lets your agent fetch live data in two lines of code.

```python
from duckduckgo_search import DDGS; results = DDGS().text('query')
```

## Step-by-step procedure

### 1. Step 1: Define your agent tools
Write standard Python functions that your agent can use, like searching the web or reading a file.

```python
def get_weather(city):
    return 'rainy in Kolkata'
```

### 2. Step 2: Describe tools using JSON schemas
Create the structure that tells the LLM what your functions do and what arguments they expect.

```
tools = [{'type': 'function', 'function': {'name': 'get_weather', 'description': 'Get current weather'}}]
```

### 3. Step 3: Set up the agent loop
Write a simple loop that calls the LLM, checks if it wants to call a tool, and executes it.

```
response = client.chat.completions.create(model='gpt-4o', messages=messages, tools=tools)
```

### 4. Step 4: Execute the tool and append results
If the LLM requests a tool call, run your local Python function with the arguments it provided, then feed the result back to the LLM.

```
tool_output = get_weather(args['city'])
messages.append({'role': 'tool', 'content': tool_output})
```

### 5. Step 5: Run and verify the agent
Run your script and ask it to do something requiring a tool, then watch it fetch the data and give you the final answered output.

```
python agent.py "What's the weather like in Kolkata?"
```

## The mistake almost everyone makes

> ⚠️  Letting the agent run without a fallback when tool execution fails. Fix this by wrapping your tool calls in a try-except block and passing the traceback back to the LLM so it can self-correct the arguments.

## X / Twitter thread (copy-paste ready)

**1/** Spent last night fighting bloated agent frameworks. Here is how to build one in 50 lines of clean Python.

**2/** Most agent libraries are just fancy wrappers around a while loop, some tools, and a system prompt. You don't need them.

**3/** Tip 1: Define your tools as plain Python functions and use Pydantic to auto-generate the JSON schemas.

**4/** Tip 2: Implement a strict max_iterations limit. Runaway agent loops will drain your OpenAI wallet in minutes.

**5/** Tip 3: Feed tool execution errors back to the LLM. It's shockingly good at fixing its own arguments if you show it the traceback.

**6/** Stop installing heavy frameworks for simple automation tasks. Build your own lightweight loop and keep full control.

## LinkedIn version

It was 1:30 AM, and I was staring at a stack trace from a popular AI agent framework. All I wanted was to search a website and summarize the text. Instead, I was debugging a nested async state manager I didn't even ask for.

So I did what any annoyed developer does. I deleted my environment, threw out the framework, and decided to build it from scratch.

Turns out, an AI Agent is just a while loop. The LLM decides if it needs a tool, you run the tool locally, append the result to the message history, and send it back. That's it. No complex abstractions, no magic classes, just pure Python.

By writing it manually, I got full visibility into the token usage, zero dependency bloat, and it actually worked on the first try. If you're building tools for production, start simple before reaching for heavy wrappers.

Here is the stack I ended up using: raw OpenAI client, Pydantic for validation, and a simple list for memory. Keep it simple.

#python #aiagents #softwareengineering #developerlife #coderfact

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*