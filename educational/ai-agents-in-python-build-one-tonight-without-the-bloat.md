# AI agents in Python: build one tonight without the bloat

_Skip the massive frameworks. Here is how to write a simple, predictable agent using just OpenAI and a loop._

## Scroll-stopping hooks

**Hook 1.** Spent three hours last night wrestling with framework abstractions just to make a simple API call. I threw it all out and wrote a 40-line Python loop instead.

**Hook 2.** Most AI agent tutorials force you into massive ecosystems you don't need. You can build a fully functional tool-calling agent with vanilla Python in ten minutes.

**Hook 3.** I was up until 2 AM trying to figure out why my agent was stuck in an infinite loop. Turns out, writing your own execution loop is better than relying on library magic.

**Hook 4.** Stop importing 50MB libraries to do basic LLM orchestration. A real AI agent is just a while-loop, a system prompt, and some JSON schemas.

**Hook 5.** If you can write a Python function and parse a dictionary, you can build an AI agent. Let's stop overcomplicating things.

## 7 tips that actually move the needle

### Tip 1. Use pydantic for tool definitions
_Why it matters:_ It guarantees the LLM outputs exactly the JSON structure your local Python functions expect.

```
class Search(BaseModel):
    query: str
```

### Tip 2. Use instructor to force JSON outputs
_Why it matters:_ It patches the OpenAI client so you get typed Pydantic objects back instead of raw, unpredictable strings.

```python
import instructor
client = instructor.from_openai(OpenAI())
```

### Tip 3. Stick to gpt-4o-mini for testing
_Why it matters:_ It is fast, incredibly cheap, and handles basic tool-calling schemas perfectly without burning through your API credits.

```
model="gpt-4o-mini"
```

### Tip 4. Set temperature to 0.0
_Why it matters:_ You want deterministic tool execution, not creative hallucinations when parsing arguments.

```
client.chat.completions.create(..., temperature=0.0)
```

### Tip 5. Use rich for terminal debugging
_Why it matters:_ Printing raw nested dicts at 1 AM will make your eyes bleed—pretty printing saves your sanity.

```python
from rich import print
print(response)
```

### Tip 6. Write a local execution sandbox
_Why it matters:_ Agents will try to run weird commands, so wrap your local tool execution in a strict try-except block.

```
try:
    res = func(**args)
except Exception as e:
    res = str(e)
```

### Tip 7. Use python-dotenv to manage keys
_Why it matters:_ Hardcoding your OpenAI key is the fastest way to get your GitHub repo scraped and your credit card maxed.

```python
from dotenv import load_dotenv
load_dotenv()
```

## Step-by-step procedure

### 1. Step 1: Set up your environment
Create a clean directory and install the bare minimum packages—just openai and python-dotenv.

```python
pip install openai python-dotenv
```

### 2. Step 2: Define your local tools
Write a simple Python function that your agent can call, like fetching stock prices or calculating a formula.

```python
def get_stock_price(ticker: str) -> str:
    return "150.00"
```

### 3. Step 3: Define the tool schema
Describe your function to the LLM using OpenAI's tool format so it knows when and how to call it.

```
tools = [{"type": "function", "function": {"name": "get_stock_price", "parameters": {...}}}]
```

### 4. Step 4: Write the orchestration loop
Send the user prompt to the LLM, check if it wants to call a tool, execute the tool locally, and send the result back.

```
res = client.chat.completions.create(messages=msgs, tools=tools)
```

### 5. Step 5: Run and verify the agent
Ask the agent a question that requires the tool, and watch it call the function and give you the final answer.

```python
print(run_agent("What is the price of AAPL?"))
```

## The mistake almost everyone makes

> ⚠️  Letting the agent run in an infinite loop when a tool fails. Fix: Always implement a max_iterations counter (e.g., max 5 loops) to force-stop the run if the LLM gets confused.

## X / Twitter thread (copy-paste ready)

**1/** AI agents in Python don't require massive, bloated frameworks. Here is how I built one in 40 lines of clean code last night.

**2/** I spent hours fighting framework magic before realizing a real agent is just a while-loop, a system prompt, and some JSON schemas.

**3/** Tip 1: Use basic Python dicts or Pydantic to define your tools. Keep the schemas dead simple so the LLM doesn't hallucinate arguments.

**4/** Tip 2: Set your temperature to 0.0. You want reliable, deterministic tool calls, not creative writing when it's parsing function arguments.

**5/** Tip 3: Wrap your tool execution loop in a strict try-except block. If a tool fails, send the error back to the LLM so it can self-correct.

**6/** Stop overcomplicating your stack. Try writing a raw loop tonight and see how much easier it is to debug. Let me know what you build!

## LinkedIn version

It was 1 AM last night, and I was staring at a stack trace from a popular AI agent framework. All I wanted was to make an LLM call a local database script. Instead, I was deep in some abstract class hierarchy trying to figure out why my agent was stuck in a recursion loop.

I got annoyed, deleted the virtualenv, and decided to write it from scratch. No bloated libraries. Just vanilla Python, the OpenAI SDK, and a simple while-loop.

Turns out, an agent is incredibly simple. You give the LLM a list of tools (which are just JSON schemas of your Python functions). You ask it a question. If it needs a tool, it returns a JSON payload. You run the function locally, feed the result back to the LLM, and repeat until it has the final answer.

Doing this raw taught me more about agent behavior than any tutorial. I had full control over the error handling, I could see exactly what tokens were being sent, and debugging took seconds instead of minutes.

If you are trying to build agents for your tools or CoderFact projects, skip the wrapper frameworks first. Build a raw loop. It will save you hours of headache and give you a much better mental model.

python
ai
development
automation

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*