import os

def execute_command(command: str) -> int:
    return os.system(command)