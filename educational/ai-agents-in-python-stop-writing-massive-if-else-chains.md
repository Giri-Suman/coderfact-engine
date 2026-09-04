# AI agents in Python: Stop writing massive if-else chains

_Build a self-correcting agent in under 50 lines of Python without paying for heavy, bloated frameworks._

## Scroll-stopping hooks

**Hook 1.** I spent three hours last night fighting with LangChain abstractions just to make a simple API call, so I threw it all out and wrote a raw Python loop instead.

**Hook 2.** You don't need a bloated framework to build an AI agent—most of it is just a while loop, a system prompt, and structured JSON outputs.

**Hook 3.** Everyone is selling 'AI agent platforms' when the core pattern is literally just: LLM generates tool call, Python runs tool, LLM gets result, repeat.

**Hook 4.** My 1 AM realization: stop trying to make your LLM smart with prompting when you can just give it a calculator and a bash shell.

**Hook 5.** I finally built an agent that actually works for my CoderFact workflows, and the secret was deleting 80% of the helper libraries I installed.

## 7 tips that actually move the needle

### Tip 1. Use pydantic for structured tool definitions
_Why it matters:_ It keeps the LLM from hallucinating invalid JSON shapes and validates arguments automatically.

```
class ToolCall(BaseModel):
  name: str
  args: dict
```

### Tip 2. Use the instructor library to patch your OpenAI client
_Why it matters:_ It forces the LLM to return clean Pydantic objects directly instead of raw string JSON.

```python
import instructor
client = instructor.from_openai(OpenAI())
```

### Tip 3. Wrap API calls with the tenacity library
_Why it matters:_ Network drops and rate limits shouldn't crash your agent loop midway through a complex task.

```python
from tenacity import retry, stop_after_attempt
@retry(stop=stop_after_attempt(3))
```

### Tip 4. Load env vars with python-dotenv
_Why it matters:_ Hardcoding API keys is the fastest way to get your account drained on GitHub.

```python
from dotenv import load_dotenv
load_dotenv()
```

### Tip 5. Use the rich library for terminal logging
_Why it matters:_ Standard print statements make debugging agent thought loops a complete nightmare.

```python
from rich import print
print('[bold green]Agent thinking...[/]')
```

### Tip 6. Run local CLI tools safely with the subprocess module
_Why it matters:_ Let your agent run local CLI tools safely instead of writing custom wrappers for everything.

```python
import subprocess
res = subprocess.run(['git', 'status'], capture_output=True)
```

### Tip 7. Use litellm to switch models instantly
_Why it matters:_ Swap between local Ollama models and Anthropic/OpenAI without changing your agent logic.

```python
from litellm import completion
res = completion(model='ollama/llama3', messages=msgs)
```

## Step-by-step procedure

### 1. Step 1: Set up your environment
Install your dependencies using pip—keep it minimal with just openai and pydantic to avoid dependency hell.

```python
pip install openai pydantic python-dotenv
```

### 2. Step 2: Define your local tools
Write a simple Python function that your agent can use, like a basic calculator or a file reader.

```python
def calculate_bonus(salary: int) -> int:
    return int(salary * 0.15)
```

### 3. Step 3: Create the system prompt
Instruct the LLM on what tools are available and force it to output a JSON string containing the tool name and arguments.

```
prompt = "You have access to: calculate_bonus. Output JSON with 'tool' and 'args'."
```

### 4. Step 4: Build the execution loop
Write a loop that sends the prompt to the LLM, parses the response, executes the local Python function, and feeds the output back to the LLM.

```
while not completed:
    # call LLM -> parse JSON -> run tool -> append to history
```

### 5. Step 5: Run and verify the agent
Ask the agent a question that requires the tool—like calculating a bonus—and print the final output to verify it didn't hallucinate the math.

```python
print(run_agent("What is the bonus for a 100k salary?"))
```

## The mistake almost everyone makes

> ⚠️  Leaving your agent loop open-ended. If the LLM gets confused, it will call the same failing tool infinitely, racking up a massive API bill in minutes. Fix this by adding a hard 'max_iterations = 5' counter inside your while loop.

## X / Twitter thread (copy-paste ready)

**1/** Spent last night rebuilding my CoderFact agent from scratch because bloated frameworks drove me crazy. Here is how to do it in pure Python.

**2/** Most agent tutorials overcomplicate things with custom graphs and state machines. At its core, an agent is just a while loop that parses JSON.

**3/** Step 1: Use Pydantic to force your LLM to output structured tool calls. No more regex parsing raw string outputs.

**4/** Step 2: Write a basic execution loop in Python that maps the LLM's requested tool name to an actual local Python function.

**5/** Step 3: Always set a strict max_iterations limit (like 5) so your agent doesn't get stuck in an expensive infinite billing loop.

**6/** Built this for my 1am automated code review tool and it runs flawlessly. Stop over-engineering your AI stack.

## LinkedIn version

It was 1 AM, and I was staring at a stack trace from a popular AI agent framework. All I wanted was to let a local LLM run a simple git command to automate a CoderFact workflow. Instead, I got 15 layers of abstract classes, helper functions, and undocumented config errors.

So I did what any annoyed developer does—I deleted node_modules (or in this case, my virtualenv), opened a clean main.py, and wrote a raw Python loop.

Here is the secret: an AI agent is not magic. It is a while loop. The LLM decides what to do, your Python environment runs the tool, and you feed the output back to the LLM. You do not need massive external frameworks to handle this. A simple combination of OpenAI's API, Pydantic for structure, and a basic dictionary mapping tool names to functions is all it takes.

Keep your agent stack simple. It makes debugging easier, keeps your API costs predictable, and actually works when you deploy it.

How are you building your agents? Let me know in the comments.

#python #aiagents #automation #backend

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*