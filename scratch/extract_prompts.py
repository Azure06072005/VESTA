import json
import pathlib
import io
import sys

conv_id = "d8334d76-6f02-4079-adcd-a6b0aac346f2"
transcript_path = pathlib.Path(f"C:/Users/ADMIN/.gemini/antigravity-ide/brain/{conv_id}/.system_generated/logs/transcript.jsonl")

with open(transcript_path, "r", encoding="utf-8") as f:
    lines = [json.loads(line) for line in f]

user_messages = []
current_user = None
dialogues = []

# We want to pair each user input with the agent's actions and responses
for i, entry in enumerate(lines):
    t_type = entry.get("type")
    src = entry.get("source")
    content = entry.get("content", "")
    tool_calls = entry.get("tool_calls", [])
    
    if t_type == "USER_INPUT":
        # Check if content has <USER_REQUEST>
        user_messages.append({"step": i, "content": content})

out_txt = []
out_txt.append(f"# Total USER_INPUT steps: {len(user_messages)}")
for idx, um in enumerate(user_messages):
    c = um['content']
    # extract user request
    if "<USER_REQUEST>" in c:
        req = c.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
    else:
        req = c.strip()
    out_txt.append(f"\n--- PROMPT {idx+1} (Step {um['step']}) ---")
    out_txt.append(req)

with open("d:/VESTA/scratch/all_prompts.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out_txt))

print("Wrote all prompts to scratch/all_prompts.txt, total:", len(user_messages))
