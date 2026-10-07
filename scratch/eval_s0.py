import json
import hashlib
import os
import subprocess

tasks = {
    '7dab0b912a43': 'task_01',
    'fdb65443317b': 'task_02',
    '8bce4c1d610d': 'task_03',
    '00b37c6e87fa': 'task_04',
    '543c2b82c895': 'task_05',
    'fca96a5e0162': 'task_06',
    'bddc46fd625d': 'task_07',
    '1988fa7c6886': 'task_08'
}

with open('research_evaluation/evaluation_prompts.jsonl') as f:
    for line in f:
        data = json.loads(line)
        prompt = data['prompt']
        prompt_id = hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:12]
        
        if prompt_id in tasks:
            task = tasks[prompt_id]
            found = False
            for model in ["gemini-3.1-pro", "gemini-3.8-flash"]:
                cache_str = f"{prompt}|{model}|0.0"
                cache_key = hashlib.sha256(cache_str.encode()).hexdigest()
                filename = f"logs/generation_cache/{cache_key}.txt"
                if os.path.exists(filename):
                    found = True
                    temp_py = f"scratch/{task}_s0.py"
                    import shutil
                    shutil.copy(filename, temp_py)
                    print(f"--- Task: {task} ---")
                    os.system(f"python -m radon cc -a -s {temp_py}")
                    os.system(f"python -m radon mi {temp_py}")
                    os.system(f"python -m py_compile {temp_py}")
                    break
            
            if not found:
                print(f"--- Task: {task} --- NOT FOUND")
