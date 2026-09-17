# AI agents in Python: build one in 15 minutes without the bloat

_Stop copy-pasting wrapper frameworks and build a real autonomous loop that actually works._

## Scroll-stopping hooks

**Hook 1.** Spent 3 hours last night fighting a massive agent framework only to realize the whole thing is just a while-loop and an LLM call.

**Hook 2.** Everyone is selling five-thousand-dollar courses on AI agents when you can build a self-correcting script in 40 lines of Python.

**Hook 3.** I stayed up until 2 AM debugging why my AI agent got stuck in an infinite loop trying to scrape its own terminal output.

**Hook 4.** If you are still using heavy libraries just to parse a basic JSON tool call, please stop—you are killing your latency.

**Hook 5.** Built a tiny agent at midnight to scrape my own blog, find dead links, and fix them—here is how to do it without the bloat.

## 7 tips that actually move the needle

### Tip 1. pydantic
_Why it matters:_ LLMs return garbage text unless you force them into a strict schema for tool calling.

```
class Action(BaseModel):
    tool: str
    query: str
```

### Tip 2. openai response_format
_Why it matters:_ It forces the model to strictly adhere to your Pydantic schema at the API level.

```
client.beta.chat.completions.parse(
    model='gpt-4o-mini',
    response_format=Action
)
```

### Tip 3. instructor
_Why it matters:_ It patches standard LLM clients to handle validation retries automatically when the JSON is slightly off.

```python
import instructor
client = instructor.from_openai(OpenAI())
```

### Tip 4. getattr()
_Why it matters:_ Don't write massive if-else blocks to map tool names to functions; resolve them dynamically.

```
func = getattr(tools_module, action.tool)
result = func(action.query)
```

### Tip 5. tenacity
_Why it matters:_ Agent loops crash constantly on rate limits or network hiccups—retry decorators save your sanity.

```python
@retry(stop=stop_after_attempt(3))
def call_llm(): pass
```

### Tip 6. rich
_Why it matters:_ Watching an agent run in a black-and-white terminal is impossible to debug; use Live consoles instead.

```python
from rich.console import Console
console = Console()
```

### Tip 7. python-dotenv
_Why it matters:_ Hardcoding API keys in an agent script is a guaranteed way to leak them on GitHub within five minutes.

```python
from dotenv import load_dotenv
load_dotenv()
```

## Step-by-step procedure

### 1. Step 1: Define your local tools
Write simple, vanilla Python functions that return strings, such as fetching a web page or reading a local file.

```python
def fetch_url(url: str) -> str:
    return requests.get(url).text
```

### 2. Step 2: Create your Pydantic schema
Define the exact structure the agent must use to choose a tool and provide the arguments.

```
class ToolCall(BaseModel):
    tool_name: str
    argument: str
```

### 3. Step 3: Write the system instructions
Tell the LLM exactly what tools are available and force it to output the JSON matching your schema.

```
prompt = "You have access to: fetch_url. Output your next action."
```

### 4. Step 4: Build the execution loop
Call the LLM, parse the tool choice, execute the local function, and feed the result back to the LLM.

```
while not finished:
    action = get_llm_action()
    result = run_tool(action)
    add_to_history(result)
```

### 5. Step 5: Run and verify the output
Test it by asking the agent to fetch a local file, extract a specific line, and write the summary to a new file.

```
python agent.py "Find the error in logs.txt and save the fix"
```

## The mistake almost everyone makes

> ⚠️  Letting the agent run without a max iteration cap, which drains your API credits in minutes. Fix this by adding a simple counter variable in your while-loop and breaking if it exceeds 5 iterations.

## X / Twitter thread (copy-paste ready)

**1/** Built my first real AI agent last night and honestly, 90% of the frameworks out there are just over-engineered wrappers.

**2/** I spent hours debugging a heavy library before throwing it away and writing a simple 50-line Python loop.

**3/** Tip 1: Use Pydantic to force the LLM to return structured JSON instead of raw text.

**4/** Tip 2: Use Python's getattr() to dynamically call your tools instead of writing endless if-else statements.

**5/** Tip 3: Always put a hard limit on your execution loop so a bug doesn't drain your wallet while you sleep.

**6/** Here is the full breakdown of how to build this lightweight setup in under 15 minutes.

## LinkedIn version

I stayed up until 2 AM last night fighting a massive agent framework that promised to build my AI agent in three lines of code. It lied. After wrestling with dependency hell and cryptic error messages, I deleted the whole thing and wrote a simple while-loop in vanilla Python.

It turns out we don't need hundreds of files of abstraction. An AI agent is just a three-step loop: ask the LLM what to do, execute the tool it chose, and feed the result back to the LLM.

I used Pydantic to force the model to output structured JSON, and Python's built-in getattr to run the tools dynamically. No heavy libraries, no bloated middleware—just clean, readable code.

The best part? It runs in milliseconds instead of seconds, and I actually understand how to debug it when it breaks.

Stop overcomplicating your stack. Build the loop yourself first so you actually know what's happening under the hood.

python
aiagents
automation
developer

_Tags: python, aiagents, automation, developer_

---
*By Suman Giri — built with the CoderFact engine.*