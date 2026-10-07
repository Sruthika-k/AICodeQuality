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
    'bddc46fd6258': 'task_07',
    '1988fa7c6886': 'task_08'
}

with open('research_evaluation/evaluation_prompts.jsonl') as f:
    for line in f:
        data = json.loads(line)
        prompt = data['prompt']
        prompt_id = hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:12]
        
        if prompt_id in tasks:
            task = tasks[prompt_id]
            cache_str = f"{prompt}|gemini-3.8-flash|0.0"
            cache_key = hashlib.sha256(cache_str.encode()).hexdigest()
            filename = f"scratch/{cache_key}.py"
            
            print(f"Task: {task}")
            
            # Radon CC Max
            cc_out = subprocess.check_output(["python", "-m", "radon", "cc", "-j", filename]).decode()
            cc_data = json.loads(cc_out)
            file_cc = cc_data.get(filename, [])
            if not file_cc:
                print("Max CC: 0, Avg CC: 0")
            else:
                max_cc = max([block.get("complexity", 0) for block in file_cc] + [0])
                avg_cc = sum(block.get("complexity", 0) for block in file_cc) / len(file_cc)
                print(f"Max CC: {max_cc}, Avg CC: {avg_cc}")
            
            # Radon MI
            mi_out = subprocess.check_output(["python", "-m", "radon", "mi", "-j", filename]).decode()
            mi_data = json.loads(mi_out)
            mi_val = mi_data.get(filename, {}).get("mi", 0)
            print(f"MI: {mi_val}")
            
            # Py Compile
            try:
                subprocess.check_call(["python", "-m", "py_compile", filename])
                print("py_compile: Passed")
            except:
                print("py_compile: Failed")
            print()
