# Build your first AI agent in Python

_Loop, tool, decide — the three pieces every agent actually needs, no LangChain wizardry required._

## Scroll-stopping hooks

**Hook 1.** Spent 2 hours trying to make an "AI agent." Turns out it's just an LLM in a while loop that calls a function. That's it. That's the whole thing.

**Hook 2.** Everyone's selling agent frameworks. I built one in 40 lines of Python and a dictionary. Here's the boring truth about what an agent actually is.

**Hook 3.** If your "agent" is a single prompt → function call → response, you don't have an agent. You have a wrapper. Real agents decide what to do next.

**Hook 4.** The LangChain docs made me feel dumb. Then I read the OpenAI function-calling page and realized I've been overthinking this for months.

**Hook 5.** An AI agent isn't magic. It's state, a prompt, a tool list, and a loop. Everything else is decoration.

## 7 tips that actually move the needle

### Tip 1. Use OpenAI's `tools=` parameter, not the deprecated `functions=`
_Why it matters:_ The new tool-calling API gives the model structured choices and works across every major provider now.

```
response = client.chat.completions.create(
  model="gpt-4o",
  messages=msgs, tools=tool_schemas
)
```

### Tip 2. Store conversation state in a plain list of dicts
_Why it matters:_ No framework needed — you can inspect, replay, and debug every turn without magic.

```
history = [{"role": "system", "content": "You are an agent."}]
```

### Tip 3. Define tools with Pydantic models + a JSON schema dump
_Why it matters:_ Type-safe tool definitions that the model can actually parse correctly.

```
class GetWeather(BaseModel):
    city: str
    schema = GetWeather.model_json_schema()
```

### Tip 4. Log every tool call to a file with `json.dump`
_Why it matters:_ When the agent does something weird at 1am, you'll thank past-you for the paper trail.

```
json.dump({"step": i, "tool": name, "args": args}, f)
```

### Tip 5. Use `tenacity` for retrying tool calls
_Why it matters:_ APIs fail, rate limits hit, and your agent shouldn't crash on a 429.

```
@retry(wait=wait_exponential(), stop=stop_after_attempt(3))
```

### Tip 6. Start with `gpt-4o-mini` while prototyping
_Why it matters:_ It's 15x cheaper and you only need the big model for the final eval pass.

## Step-by-step procedure

### 1. Install the basics
You need the OpenAI SDK and Pydantic. Nothing else.

```python
pip install openai pydantic tenacity
```

### 2. Define two or three tools as plain Python functions
Keep them simple — a calculator, a web fetcher, a file reader. Each one returns a string the LLM can read.

```python
def get_weather(city: str) -> str:
    return f"It's 22°C and clear in {city}."
```

### 3. Convert tools to JSON schemas the model can see
Pydantic gives you this for free via `model_json_schema()`. The model picks which tool to call based on these.

```
tools = [
    {"type": "function", "function": {"name": "get_weather", "parameters": GetWeather.model_json_schema()}}
]
```

### 4. Write the agent loop
Call the model, if it wants a tool, run it, append the result to messages, repeat. That's the whole engine.

```
for step in range(max_steps):
    resp = client.chat.completions.create(model=MODEL, messages=msgs, tools=tools)
    if not resp.choices[0].message.tool_calls:
        break
    msgs.append(execute_tool(resp.choices[0].message.tool_calls[0]))
```

### 5. Verify it works with a multi-step question

### 6. Add error handling and logging
Wrap tool calls in try/except, log to a file, retry on failure. This is what separates a demo from a thing you'd actually run.

## The mistake almost everyone makes

> ⚠️  Forgetting to append the assistant's tool-call message back to the conversation before sending the tool result. The model loses context and either loops forever or hallucinates. Fix: always push `msg.tool_calls[0]` to `messages` first, then push the tool response.

_Tags: python, tutorial, ai, developer_

---
*By Suman Giri — built with the CoderFact engine.*