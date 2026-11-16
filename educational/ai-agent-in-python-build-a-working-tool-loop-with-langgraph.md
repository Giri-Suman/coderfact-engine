# AI Agent in Python: Build a working tool loop with LangGraph

_Stop paying for wrapper apps—build a local execution loop that actually does work in 50 lines of code._

## Scroll-stopping hooks

**Hook 1.** Most AI agent frameworks are just overengineered string formatters that hide the actual execution loop. Here's how to build one in pure Python without the abstractions.

**Hook 2.** Spent until 1:30 AM debugging an agent that kept calling the same web search tool infinitely. The fix isn't more prompts—it's typed state management.

**Hook 3.** If your AI agent breaks the moment a tool returns invalid JSON, you don't need a smarter model. You need a structured schema boundary.

**Hook 4.** Built a local file-organizing agent last night because I got tired of drag-and-dropping PDFs into subfolders like it's 2004.

**Hook 5.** You don't need AutoGPT or an enterprise agent platform. A while loop, standard library exec/tools, and structured output get you 90% of the way there.

## 7 tips that actually move the needle

### Tip 1. Use Pydantic's BaseModel to define tool arguments explicitly
_Why it matters:_ LLMs hallucinate parameter names unless forced into a strict, machine-readable JSON schema.

```
class SearchInput(BaseModel):
    query: str = Field(description="The search query string")
```

### Tip 2. Set binding constraints using `llm.bind_tools()` in LangChain/LangGraph
_Why it matters:_ It passes raw JSON schemas directly to the API boundary instead of relying on systemic prompt instructions.

```
tools = [fetch_page, run_sql]
llm_with_tools = ChatOpenAI(model="gpt-4o").bind_tools(tools)
```

### Tip 3. Enforce strict state typing using Typing.TypedDict for your agent graph
_Why it matters:_ It stops message list corruption as state passes between conditional nodes.

```
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
```

### Tip 4. Add a hard iteration limit inside your graph conditional edges
_Why it matters:_ An infinite tool-execution loop will drain your OpenAI API credits before you wake up.

```python
def should_continue(state):
    return "end" if len(state["messages"]) > 10 else "continue"
```

### Tip 5. Wrap custom Python tools with `@tool` from `langchain_core.tools`
_Why it matters:_ It automatically converts docstrings and typing annotations into native LLM tool definitions.

```python
@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
```

### Tip 6. Use SystemMessage to set absolute operational boundaries before user input
_Why it matters:_ It prevents the model from attempting to run non-existent tools when missing context.

```
sys_msg = SystemMessage(content="Only use tools if explicit data is requested.")
```

### Tip 7. Inspect raw tool responses with `langchain.debug = True`
_Why it matters:_ It prints the exact payload sent to and returned by API endpoints so you can fix schema mismatches fast.

```python
import langchain
langchain.debug = True
```

## Step-by-step procedure

### 1. Step 1: Install target dependencies
Pull in the core packages for modern, typed agent loops without bloated legacy extras.

```python
pip install langgraph langchain-openai pydantic
```

### 2. Step 2: Define your core tools
Decorate typed Python functions to act as tools the agent can invoke.

```python
from langchain_core.tools import tool

@tool
def read_file(path: str) -> str:
    """Reads contents of a text file at path."""
    with open(path, 'r') as f:
        return f.read()
```

### 3. Step 3: Setup the model and tool bindings
Initialize your model client and bind the executable tools directly.

```python
from langchain_openai import ChatOpenAI

tools = [read_file]
model = ChatOpenAI(model="gpt-4o", temperature=0).bind_tools(tools)
```

### 4. Step 4: Construct the StateGraph loop
Define state and wire up conditional edges to handle model decisions versus tool calls.

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

builder = StateGraph(AgentState)
builder.add_node("agent", call_model)
builder.add_node("tools", ToolNode(tools))
builder.add_conditional_edges("agent", should_continue)
```

### 5. Step 5: Compile and run a live file test
Execute the compiled graph with an actual request requiring file access to verify tool execution.

```python
app = builder.compile()
res = app.invoke({"messages": [("user", "read notes.txt and summarize it")]})
print(res["messages"][-1].content)
```

## The mistake almost everyone makes

> ⚠️  Passing untyped dictionaries into custom tool signatures. The LLM guesses parameter names like 'file' instead of 'filename', causing key errors. Always fix this by using Pydantic schemas or explicit type annotations on `@tool` functions.

## X / Twitter thread (copy-paste ready)

**1/** Most Python agent tutorials make you install 15 bloatware packages just to run a web search. Here is how to build a clean tool loop with LangGraph in under 50 lines.

**2/** Spent way too long last night fixing agent loops that got stuck repeating tool calls. The issue is almost always untyped function arguments and bad graph logic.

**3/** 1/ Use @tool decorators with explicit type hints. The model needs parameter descriptions to call functions without guessing schema keys.

**4/** 2/ Bind tools directly to the model with .bind_tools(). Don't pass system prompts asking the model to output raw JSON strings manually.

**5/** 3/ Wire up a StateGraph with explicit conditional edges. Always cap maximum message depth so a failing tool doesn't burn through $50 of API credits.

**6/** Build the loop, run it against real local files, keep abstractions minimal. What tools are you hooking up to your local setups?

## LinkedIn version

I stayed up until 1:30 AM last night fighting a recursive execution bug in a custom Python agent.

Every time it ran a local search function, it parsed the returned output as a brand-new user request, re-triggered the tool, and fell into a doom loop. Mildly annoying, but standard for custom agent development.

The real problem isn't the AI—it's how we wrap its interfaces. Most devs throw massive high-level frameworks at the problem, hoping the tool abstraction figures out state management for them. It doesn't.

Building a working agent comes down to three explicit mechanics: strict Pydantic inputs for tool arguments, a typed state schema, and hard iteration limits. Once you lock those down in pure Python and LangGraph, the agent actually executes reliable workflows without hallucinating tool inputs.

Stop relying on massive wrapper apps to automate small dev chores. Define your tools, bind them cleanly, and let the model work within strict typed guardrails.

#python #aiengineering #langchain #softwaredevelopment

_Tags: python, aiagents, langgraph, backend_

---
*By Suman Giri — built with the CoderFact engine.*