# AI Agents in Python: Build One Tonight with LangGraph

_Stop overcomplicating agent loops. Here is a 15-line script that actually works._

## Scroll-stopping hooks

**Hook 1.** I spent 3 hours last night debugging an 'intelligent' agent only to realize it was stuck in an infinite while loop calling OpenAI.

**Hook 2.** Most AI agent tutorials hand you a 400-line framework setup when all you actually needed was a python dictionary and a while loop.

**Hook 3.** Stop using complex agent frameworks until you've written a basic decision loop in pure Python first.

**Hook 4.** Your first AI agent shouldn't cost $12 in API credits just to parse a CSV file.

**Hook 5.** I finally stopped overengineering my Python agents at 1am, and the fix was surprisingly simple.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to enforce structured output from your LLM calls
_Why it matters:_ Raw text responses break your parser half the time, but Pydantic guarantees valid JSON schema.

```python
from pydantic import BaseModel
class Action(BaseModel):
    tool: str
    query: str
```

### Tip 2. Bind tools directly using langchain-openai or raw OpenAI function calling
_Why it matters:_ It stops the model from hallucinating non-existent function names by constraining the API call.

```
tools = [search_db, fetch_url]
llm_with_tools = llm.bind_tools(tools)
```

### Tip 3. Set an explicit recursion_limit inside your state graph
_Why it matters:_ Without a cap, a confused model will burn your entire API budget in four minutes.

```
app = workflow.compile()
app.invoke(input_data, config={"recursion_limit": 5})
```

### Tip 4. Log raw LLM responses to a local SQLite database using loguru
_Why it matters:_ You cannot debug non-deterministic agent loops without seeing the exact payload that triggered the loop.

```python
from loguru import logger
logger.add("agent_debug.log", level="DEBUG")
```

### Tip 5. Use python-dotenv to isolate your key management completely
_Why it matters:_ Hardcoding API keys inside agent scripts is how dev accounts get compromised on GitHub overnight.

```python
from dotenv import load_dotenv
import os
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
```

### Tip 6. Implement a manual human-in-the-loop interruption step
_Why it matters:_ It prevents your agent from executing destructive local system commands without your approval.

```
workflow.compile(interrupt_before=["execute_command"])
```

### Tip 7. Test agent tools in isolation with pytest before attaching them to the LLM
_Why it matters:_ If your underlying python tool fails, the LLM will try to guess why and hallucinate wildly.

```python
def test_calculator():
    assert run_calculator("2+2") == 4
```

## Step-by-step procedure

### 1. Install the essential dependencies
Grab LangGraph and the OpenAI integration package to keep your graph logic clean and lightweight.

```python
pip install langgraph langchain-openai python-dotenv
```

### 2. Define your state schema
Create a typed dictionary that holds the message history across every loop execution.

```python
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
```

### 3. Create a concrete Python tool
Write the function your agent will run when it needs to interact with the external world.

```python
from langchain_core.tools import tool

@tool
def add_numbers(a: int, b: int) -> int:
    """Adds two integers together."""
    return a + b
```

### 4. Build the execution graph
Connect your LLM node and tool execution node inside a StateGraph object.

```python
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

builder = StateGraph(AgentState)
builder.add_node("tools", ToolNode([add_numbers]))
# Attach model node and define conditional edges here
```

### 5. Compile and invoke the graph
Run the compiled agent with a prompt requiring tool usage, and watch it resolve the execution loop.

```python
graph = builder.compile()
response = graph.invoke({"messages": [("user", "What is 42 plus 88?")]})
print(response["messages"][-1].content)
```

## The mistake almost everyone makes

> ⚠️  Passing unstructured text prompts to an LLM and trying to regex-parse the action choice out of the response. Fix this by using native function calling bindings or Pydantic output parsers so the model returns strict, machine-readable structured JSON every single time.

## X / Twitter thread (copy-paste ready)

**1/** I stayed up till 1am fighting an AI agent loop that kept hallucinating inputs. Here is how to build one that actually works in Python.

**2/** Most tutorials sell you 500 lines of abstract framework code. You don't need it. An agent is just an LLM bound to functions inside a while loop.

**3/** Tip 1: Define explicit tool functions using @tool annotations instead of asking the model to output raw string commands.

**4/** Tip 2: Use LangGraph to handle state propagation. It replaces brittle manual while-loops with explicit, traceable execution edges.

**5/** Tip 3: Always pass an explicit recursion limit to your graph runner so a confused model doesn't drain your API balance.

**6/** Drop the overengineered frameworks, start with basic function binding, and build clean execution loops. What are you building this week?

## LinkedIn version

I spent half of last night staring at a terminal output watching an AI agent loop indefinitely while consuming my OpenAI credits.

It was trying to parse its own text output using regex—and failing every single turn. At 1am, I scrapped the whole setup and rebuilt it from scratch using plain Python function binding and a simple state graph.

The real secret to reliable AI agents isn't adding more abstract framework layers. It's giving the model zero room for formatting ambiguity. When you bind tools explicitly and enforce structured schemas through Pydantic, the agent stops guessing and starts executing.

Start small: write a single Python tool, bind it to an execution node, set a hard recursion limit, and trace every state change. If you can't trace the loop manually, the LLM will definitely get lost in it.

What kind of automation tasks are you trying to offload to local agents right now?

#python #aiengineering #automation #backenddev #langchain

_Tags: python, tutorial, ai, developer_

---
*By Suman Giri — built with the CoderFact engine.*