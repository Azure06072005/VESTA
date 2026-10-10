import json
import pathlib
import io
import sys

conv_id = "d8334d76-6f02-4079-adcd-a6b0aac346f2"
transcript_path = pathlib.Path(f"C:/Users/ADMIN/.gemini/antigravity-ide/brain/{conv_id}/.system_generated/logs/transcript.jsonl")

with open(transcript_path, "r", encoding="utf-8") as f:
    lines = [json.loads(line) for line in f]

user_indices = []
for i, entry in enumerate(lines):
    if entry.get("type") == "USER_INPUT":
        user_indices.append(i)

turns_data = []

for k in range(len(user_indices)):
    start_idx = user_indices[k]
    end_idx = user_indices[k+1] if k+1 < len(user_indices) else len(lines)
    
    user_entry = lines[start_idx]
    user_raw = user_entry.get("content", "")
    if "<USER_REQUEST>" in user_raw:
        user_text = user_raw.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
    else:
        user_text = user_raw.strip()
        
    # Find the final text response from the model in this turn range
    final_response = ""
    key_actions = []
    
    for j in range(start_idx + 1, end_idx):
        entry = lines[j]
        # Collect tool actions
        if "tool_calls" in entry and entry["tool_calls"]:
            for tc in entry["tool_calls"]:
                name = tc.get("name")
                args = tc.get("args", {})
                if name == "replace_file_content" or name == "write_to_file":
                    tgt = args.get("TargetFile", "").replace("d:\\VESTA\\", "")
                    desc = args.get("Description", "")
                    key_actions.append(f"Chỉnh sửa/Tạo tệp: `{tgt}` ({desc})")
                elif name == "run_command":
                    cmd = args.get("CommandLine", "")
                    if len(cmd) < 80:
                        key_actions.append(f"Thực thi lệnh: `{cmd}`")
                    else:
                        key_actions.append(f"Thực thi lệnh: `{cmd[:60]}...`")
        
        # Check model response
        if entry.get("source") == "MODEL":
            c = entry.get("content", "")
            # If no tool calls in this entry or it is the last message before next user prompt
            if c and not entry.get("tool_calls"):
                final_response = c

    turns_data.append({
        "turn": k + 1,
        "user_prompt": user_text,
        "key_actions": key_actions,
        "final_response": final_response
    })

print(f"Extracted {len(turns_data)} turns.")
for td in turns_data:
    print(f"Turn {td['turn']}: user len={len(td['user_prompt'])}, actions={len(td['key_actions'])}, response len={len(td['final_response'])}")

with open("d:/VESTA/scratch/turns_summary.json", "w", encoding="utf-8") as f:
    json.dump(turns_data, f, ensure_ascii=False, indent=2)
print("Saved turns_summary.json successfully.")
