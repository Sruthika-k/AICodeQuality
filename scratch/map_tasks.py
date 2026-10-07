import json
import hashlib
import os

with open('research_evaluation/evaluation_prompts.jsonl') as f:
    for line in f:
        data = json.loads(line)
        prompt = data['prompt']
        prompt_id = hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:12]
        
        # the model seems to be gemini-3.8-flash and temp 0.0 based on runs.csv
        cache_str = f"{prompt}|gemini-3.8-flash|0.0"
        cache_key = hashlib.sha256(cache_str.encode()).hexdigest()
        
        print(f"Task ID: {data['id']}")
        print(f"Prompt ID (Hash): {prompt_id}")
        print(f"Cache Key (Filename): {cache_key}.txt")
        print("---")
