import json
import pathlib

conv_id = "d8334d76-6f02-4079-adcd-a6b0aac346f2"
transcript_path = pathlib.Path(f"C:/Users/ADMIN/.gemini/antigravity-ide/brain/{conv_id}/.system_generated/logs/transcript.jsonl")

if not transcript_path.exists():
    print("Transcript not found at", transcript_path)
    # Check parent dir
    parent = transcript_path.parent
    if parent.exists():
        print("Parent contents:", list(parent.iterdir()))
else:
    print("Transcript found! Size:", transcript_path.stat().st_size)
    with open(transcript_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    print("Total lines in transcript:", len(lines))
    
    turns = []
    for i, line in enumerate(lines):
        try:
            d = json.loads(line)
            src = d.get("source")
            t_type = d.get("type")
            content = d.get("content", "")
            if t_type == "USER_INPUT":
                turns.append({"role": "user", "step": i, "content": content})
            elif src == "MODEL" and content and ("tool_calls" not in d or not d.get("tool_calls")):
                # Assistant text response
                turns.append({"role": "assistant", "step": i, "content": content[:500]})
        except Exception as e:
            pass
    print("Found turns:", len(turns))
    for idx, turn in enumerate(turns):
        print(f"[{idx}] {turn['role']} (step {turn['step']}): {turn['content'][:120]}...\n")
