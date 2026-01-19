"""Vessel loader - parses memory.txt and system.txt"""
import re
from pathlib import Path
from typing import Dict

class Vessels:
    """Load and manage user vessels and system facts"""
    
    def __init__(self):
        self.vessels = self._load_file("memory/memory.txt", "vessel")
        self.system_facts = self._load_file("memory/system.txt", "system")
    
    def _load_file(self, filepath: str, prefix: str) -> Dict:
        """Parse memory file into dictionary"""
        path = Path(filepath)
        if not path.exists():
            return {}
        
        facts = {}
        for line in path.read_text().splitlines():
            match = re.match(rf'{prefix} (\d+): (\w+) = (.+)', line.strip())
            if match:
                num, key, value = match.groups()
                facts[key] = {
                    'value': value.strip(),
                    'number': num,
                    'type': prefix
                }
        return facts
    
    def get_all_text(self) -> str:
        """Get all vessels as text for AI prompt injection"""
        if not self.vessels:
            return ""
        
        lines = ["[USER FACTS - Reference when relevant:]"]
        for key, data in self.vessels.items():
            lines.append(f"vessel {data['number']}: {key} = {data['value']}")
        lines.append("[END USER FACTS]")
        return "\n".join(lines)
