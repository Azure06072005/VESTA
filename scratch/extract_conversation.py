import json
import pathlib

conv_id = "d8334d76-6f02-4079-adcd-a6b0aac346f2"
transcript_path = pathlib.Path(f"C:/Users/ADMIN/.gemini/antigravity-ide/brain/{conv_id}/.system_generated/logs/transcript.jsonl")

with open(transcript_path, "r", encoding="utf-8") as f:
    lines = [json.loads(line) for line in f]

# Find all user input step indices
user_indices = []
for i, entry in enumerate(lines):
    if entry.get("type") == "USER_INPUT":
        user_indices.append(i)

print("User indices:", user_indices)

# For each user prompt range [user_indices[k], user_indices[k+1] or end], find the assistant's final text messages
conversations = []
for k in range(len(user_indices)):
    start_idx = user_indices[k]
    end_idx = user_indices[k+1] if k+1 < len(user_indices) else len(lines)
    
    user_entry = lines[start_idx]
    user_raw = user_entry.get("content", "")
    if "<USER_REQUEST>" in user_raw:
        user_text = user_raw.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
    else:
        user_text = user_raw.strip()
        
    # Collect all assistant messages in this window that are not just tool outputs
    assistant_replies = []
    tools_used = []
    
    for j in range(start_idx + 1, end_idx):
        entry = lines[j]
        # check tool calls
        if "tool_calls" in entry and entry["tool_calls"]:
            for tc in entry["tool_calls"]:
                tool_name = tc.get("name") or tc.get("type")
                if tool_name not in tools_used:
                    tools_used.append(tool_name)
        # Check if model response with content and no tool_calls
        if entry.get("source") == "MODEL" and entry.get("content"):
            content = entry.get("content", "")
            # filter out internal tool responses or small status strings if any
            if len(content) > 100:
                assistant_replies.append(content)
                
    conversations.append({
        "turn": k + 1,
        "user_prompt": user_text,
        "tools_used": tools_used,
        "replies": assistant_replies,
        "reply_count": len(assistant_replies)
    })

print(f"Processed {len(conversations)} conversation turns.")
for c in conversations:
    print(f"Turn {c['turn']}: user len={len(c['user_prompt'])}, replies={c['reply_count']}, tools={c['tools_used'][:5]}")
    if c['replies']:
        print(f"  Last reply preview: {c['replies'][-1][:120]}...\n")
