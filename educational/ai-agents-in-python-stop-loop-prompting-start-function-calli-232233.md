# AI Agents in Python: Stop Loop-Prompting, Start Function Calling

_How I finally got a Python script to execute actual code instead of hallucinating steps at 1 AM._

## Scroll-stopping hooks

**Hook 1.** Most people build AI 'agents' by passing massive system prompts into a while loop and praying it doesn't crash.

**Hook 2.** I spent three hours debugging an AI agent last night only to realize I was overthinking function calls.

**Hook 3.** If your AI agent needs a 500-word prompt to pick a tool, you're not building an agent—you're writing a fragile parser.

**Hook 4.** Stop using raw string parsing to get structured output from LLMs in Python.

**Hook 5.** An AI agent is literally just a loop, a prompt, and a list of callable Python functions with type hints.

## 7 tips that actually move the needle

### Tip 1. Use pydantic-ai or instructor for strict JSON outputs
_Why it matters:_ It forces the LLM to return data that matches your exact Pydantic schema without manual regex parsing.

```
class SearchResult(BaseModel):
    url: str
    summary: str
```

### Tip 2. Expose Python functions directly using OpenAI tool calls
_Why it matters:_ The model natively decides when to invoke your function based on docstrings and signatures.

```python
@agent.tool
def fetch_db(query: str) -> str:
    return db.search(query)
```

### Tip 3. Cap your execution loop with an explicit max_iterations variable
_Why it matters:_ An infinite loop will drain your API credits before you wake up in the morning.

```
MAX_TURNS = 5
for _ in range(MAX_TURNS):
    response = client.step()
```

### Tip 4. Inject system execution logs back into the message history
_Why it matters:_ When a tool fails, the model needs to see the exact traceback to correct its next move.

```
messages.append({'role': 'tool', 'content': str(error)})
```

### Tip 5. Use LiteLLM to swap model providers without changing your agent logic
_Why it matters:_ It provides a unified interface for OpenAI, Anthropic, and local Ollama models.

```python
from litellm import completion
res = completion(model='ollama/llama3', messages=m)
```

### Tip 6. Isolate tool execution using subprocess or isolated environments
_Why it matters:_ Giving an LLM direct access to os.system without sandboxing is asking for a wiped directory.

```
subprocess.run(['python', '-c', code], timeout=5, capture_output=True)
```

### Tip 7. Log token usage per turn with structlog
_Why it matters:_ Agentic loops stack context rapidly—you need to track prompt bloat in real time.

```
log.info('step_complete', tokens=response.usage.total_tokens)
```

## Step-by-step procedure

### 1. Install the pydantic-ai package
Grab the lightweight framework that handles system prompts and tool schemas without the heavy abstraction of LangChain.

```python
pip install pydantic-ai logfire
```

### 2. Define your tools as plain typed functions
Write the actual Python code your agent will execute. Use clean docstrings—the model reads them.

```python
def calculate_tax(amount: float) -> float:
    """Calculates standard tax rate for an amount."""
    return amount * 0.18
```

### 3. Initialize the agent with your toolset
Bind the tool to the Agent instance and specify your model target.

```python
from pydantic_ai import Agent
agent = Agent('openai:gpt-4o', tools=[calculate_tax])
```

### 4. Run the execution loop with a user prompt
Pass the user request into the run method. The framework handles the back-and-forth tool invocations automatically.

```
result = agent.run_sync('Calculate tax for $250 invoice')
```

### 5. Verify tool execution in the output response
Check that the final output includes the computed tool result rather than a hardcoded text guess.

```python
print(result.data)
# Output: 45.0
```

## The mistake almost everyone makes

> ⚠️  Writing manual string splitters to parse LLM decisions from raw text. Use native API tool calling or Pydantic validation instead—it eliminates 99% of JSON syntax errors.

## X / Twitter thread (copy-paste ready)

**1/** Most developers overcomplicate AI agents with massive frameworks when all you need is a clean loop and typed functions.

**2/** Last night at 1am I finally tore out 200 lines of custom string parsing code. Here is how to actually build an agent in Python.

**3/** First rule: stop parsing raw text response. Use tool calling or Pydantic schemas so the LLM returns typed parameters natively.

**4/** Second rule: put a hard cap on your loop iterations. If your agent hasn't solved the task in 5 turns, it's stuck in a hallucination loop.

**5/** Third rule: feed raw execution errors back into the chat history so the model can self-correct instead of crashing your script.

**6/** Build light, use native function calls, and save your API bill. What tool-calling library are you using right now?

## LinkedIn version

I stayed up until 1 AM last night fighting a custom AI agent script.

It was supposed to fetch data from an API, format it, and send a summary. Instead, it got stuck in an infinite loop, hallucinating parameters for a function that didn't exist, burning through API tokens.

The mistake? I was treating the LLM like a magic engine and trying to parse its raw text output with custom logic. 

Building an agent doesn't require a bloated framework or 500 lines of orchestration code. Strip away the hype, and an agent is just three components: a defined goal, typed Python functions, and a loop that feeds execution results back to the model.

When you use explicit function calling—supported natively by modern models and light wrappers like Pydantic AI—the model decides *which* function to call based on your Python docstrings. No manual JSON parsing required.

Stop overbuilding your agent architecture. Start with basic typed functions, set strict iteration limits, and let the model handle tool selection.

#python #aiengineering #automation #backend #developers

_Tags: python, tutorial, ai, developer_

---
*By Suman Giri — built with the CoderFact engine.*