import ast
import json
import os
import shlex
import subprocess
from typing import Any, List, Optional, Union

class SecureData:
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> None:
        self.username: str = username or os.getenv("APP_USERNAME", "guest")
        self.password: str = password or os.getenv("APP_PASSWORD", "")
        self.api_key: str = api_key or os.getenv("APP_API_KEY", "")

    def load_data(self, filepath: str) -> Any:
        with open(filepath, "r", encoding="utf-8") as file:
            return json.load(file)

    def execute_command(self, command: Union[str, List[str]]) -> subprocess.CompletedProcess:
        if isinstance(command, str):
            command = shlex.split(command)
        return subprocess.run(
            command,
            shell=False,
            check=True,
            capture_output=True,
            text=True
        )

    def evaluate_input(self, expression: str) -> Any:
        return ast.literal_eval(expression)