# AI Agent in Python: Stop using raw API wrappers

_Build a real agent that loops, uses tools, and fixes its own mistakes in 30 lines of code._

## Scroll-stopping hooks

**Hook 1.** I stayed up till 2 AM trying to make an AI agent in Python, only to realize I was overcomplicating a basic while-loop.

**Hook 2.** Most tutorials force you into massive frameworks just to call a web search function from Python. Here is how to build an agent without the bloat.

**Hook 3.** If your Python AI script can't call a local function and inspect the output, it’s just a fancy chat box, not an agent.

**Hook 4.** Stop pip installing 15 dependencies to build a simple task-running agent—you only need basic Python and a clean decision loop.

**Hook 5.** I was mildly annoyed at how overengineered 'agentic AI' sounded until I wrote a 30-line while-loop that handled my terminal commands.

## 7 tips that actually move the needle

### Tip 1. Use LangChain's `@tool` decorator to auto-generate JSON schemas for your functions.
_Why it matters:_ It handles the tedious schema generation that LLMs require to know your function exists.

```python
from langchain_core.tools import tool
@tool
def get_weather(city: str) -> str:
    """Fetches current weather for a city."""
    return f"Sunny in {city}"
```

### Tip 2. Bind tools directly to ChatOpenAI instead of writing raw system prompts.
_Why it matters:_ It forces the LLM to return a structured tool call object instead of messy text you have to parse.

```
llm = ChatOpenAI(model="gpt-4o-mini")
llm_with_tools = llm.bind_tools([get_weather])
```

### Tip 3. Use a simple execution loop to handle `tool_calls` sequentially.
_Why it matters:_ Your agent needs to actually run the function the LLM picked and send the answer back.

```
for tool_call in response.tool_calls:
    res = tools_map[tool_call["name"]].invoke(tool_call["args"])
```

### Tip 4. Append tool outputs back to your `messages` array as `ToolMessage` instances.
_Why it matters:_ The model won't know the result of its action unless you explicitly feed it back into the context history.

```python
from langchain_core.messages import ToolMessage
messages.append(ToolMessage(content=str(res), tool_call_id=tool_call["id"]))
```

### Tip 5. Cap your loop with `max_iterations = 5` to prevent infinite API spend.
_Why it matters:_ Agents can easily get stuck in a bug loop calling the same broken tool forever.

```
count = 0
while response.tool_calls and count < 5:
    count += 1
```

### Tip 6. Use `python-dotenv` to manage your API keys silently.
_Why it matters:_ Hardcoding API tokens in your agent scripts is a fast track to committing secrets to GitHub.

```python
from dotenv import load_dotenv
load_dotenv()
```

### Tip 7. Log raw LLM responses using `langchain.debug = True` when tool calls silently fail.
_Why it matters:_ It reveals whether the model generated bad arguments or just hallucinated the tool name.

```python
import langchain
langchain.debug = True
```

## Step-by-step procedure

### 1. Step 1: Install minimal dependencies
Grab just the essential packages needed to run OpenAI models and handle tool binding.

```python
pip install langchain-openai python-dotenv
```

### 2. Step 2: Define your Python tools
Write standard Python functions and wrap them with the `@tool` decorator so the model understands their purpose.

```python
from langchain_core.tools import tool

@tool
def multiply(a: int, b: int) -> int:
    """Multiply two integers together."""
    return a * b
```

### 3. Step 3: Bind tools to the model
Initialize the OpenAI chat model and pass your tools into `bind_tools`.

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [multiply]
llm_with_tools = llm.bind_tools(tools)
```

### 4. Step 4: Build the execution loop
Pass the conversation history to the model, check if it wants to invoke a tool, execute it locally, and append the result.

```python
from langchain_core.messages import HumanMessage, ToolMessage

messages = [HumanMessage(content="What is 14 multiplied by 82?")]
response = llm_with_tools.invoke(messages)
messages.append(response)

if response.tool_calls:
    for call in response.tool_calls:
        result = multiply.invoke(call["args"])
        messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
    final_response = llm_with_tools.invoke(messages)
```

### 5. Step 5: Verify the agent result
Print the content of the final message to confirm the LLM used the returned tool output to answer your prompt accurately.

```python
print(final_response.content)
# Output: 14 multiplied by 82 is 1148.
```

## The mistake almost everyone makes

> ⚠️  Forgetting to return a `ToolMessage` with the exact `tool_call_id` back to the model. If you just append a normal `AIMessage` or `HumanMessage` with the output, OpenAI's API will crash with an invalid payload error. Always match the model's generated `tool_call_id` when appending execution results.

## X / Twitter thread (copy-paste ready)

**1/** Building an AI agent in Python isn't black magic—it's just a loop with tools. Here is how to build one in 5 steps. 🧵

**2/** Spent way too much time overthinking this at 1 AM. An 'agent' is literally just an LLM deciding to call a local Python function, getting the result, and finishing the task.

**3/** First, define your tools using LangChain's `@tool` decorator. Clear docstrings are non-negotiable—the LLM reads them to decide which tool to use.

**4/** Second, bind those tools to `ChatOpenAI(model='gpt-4o-mini')`. This forces structured JSON outputs instead of raw text you have to regex parse.

**5/** Third, run a loop. If the model output contains `tool_calls`, execute that tool locally and append the result as a `ToolMessage` matching the original ID.

**6/** That's it. No bloated agent frameworks needed. Try building a simple math or terminal agent tonight and see how straightforward it actually is.

## LinkedIn version

I stayed up past 1 AM trying to build a basic task-running agent in Python.

Every tutorial insisted I needed massive agentic frameworks, vector stores, and complex state graphs. I felt mildly annoyed at how overengineered everything was for a process that boils down to a few lines of logic.

At its core, an AI agent is just an LLM running inside a loop—deciding if it needs to call a local Python function, reading the execution output, and deciding what to do next.

To build one, you only need three core concepts: standard Python functions decorated as tools, tool-binding on the LLM client, and a basic loop that feeds `ToolMessage` results back into your chat history.

Stop overcomplicating agent architectures before you even write your first script. Build a simple while-loop agent first, figure out where it breaks, and scale up from there.

#python #aiengineering #softwaredevelopment #coding #aiagents

_Tags: python, aiagents, langchain, openai_

---
*By Suman Giri — built with the CoderFact engine.*