import redis
import subprocess
import json
import time
import reverse_geocoder as rg

class WinterCore:
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    def get_all_projects(self):
        all_keys = self.redis.keys('project:*')
        projects = {}
        for key in all_keys:
            parts = key.split(':')
            if len(parts) >= 2:
                proj = parts[1]
                if proj not in projects:
                    projects[proj] = 0
                projects[proj] += 1
        return projects
    
    def get_project_memory(self, project):
        memory = {}
        for key in self.redis.keys(f"project:{project}:*"):
            value = self.redis.get(key)
            if value:
                memory[key] = value
        return memory
    
    def geocode(self, lat, lon):
        """Offline geocoding"""
        try:
            result = rg.search((lat, lon))[0]
            return f"{result['name']}, {result['admin1']}, {result['cc']}"
        except:
            return None
    
    def detect_coordinates(self, text):
        """Detect coordinates in user input"""
        import re
        # Match formats like: 32.7417, -117.0536 or (32.7417, -117.0536)
        pattern = r'(-?\d+\.?\d*),\s*(-?\d+\.?\d*)'
        match = re.search(pattern, text)
        if match:
            lat, lon = float(match.group(1)), float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return (lat, lon)
        return None
    
    def sculpt_memory(self, project, user_input, assistant_response):
        truncated_response = assistant_response[:500] if len(assistant_response) > 500 else assistant_response
        
        prompt = f"""Analyze conversation for project {project}.

User: {user_input[:200]}
AI: {truncated_response}

Extract key info as JSON only:
{{"immutable_facts": {{}}, "mutable_state": {{}}, "outcomes": []}}"""
        
        try:
            result = subprocess.run(['ollama', 'run', 'deepseek-r1:8b', prompt],
                                  capture_output=True, text=True, timeout=60)
            
            text = result.stdout
            if "...done thinking." in text:
                text = text.split("...done thinking.")[-1]
            
            text = text.strip().replace('```json', '').replace('```', '').strip()
            data = json.loads(text)
            
            for k, v in data.get('immutable_facts', {}).items():
                self.redis.set(f"project:{project}:facts:{k}", json.dumps(v))
            
            for k, v in data.get('mutable_state', {}).items():
                self.redis.set(f"project:{project}:state:{k}", json.dumps(v))
            
            for i, o in enumerate(data.get('outcomes', [])):
                self.redis.set(f"project:{project}:outcomes:{int(time.time())}_{i}", json.dumps(o))
        except:
            pass
    
    def chat(self, project, user_input, memory):
        # Auto-detect and geocode coordinates
        coords = self.detect_coordinates(user_input)
        location_info = ""
        if coords:
            location = self.geocode(coords[0], coords[1])
            if location:
                location_info = f"\n[Coordinates detected: {coords[0]}, {coords[1]} = {location}]"
        
        memory_str = json.dumps(memory, indent=2)[:800] if memory else "{}"
        
        prompt = f"""You are agentWinter, a helpful AI assistant.

Project: {project}
Memory: {memory_str}{location_info}

User: {user_input}
agentWinter:"""
        
        process = subprocess.Popen(
            ['ollama', 'run', 'deepseek-r1:8b', prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1
        )
        
        in_thinking = False
        
        for line in process.stdout:
            if "Thinking..." in line:
                in_thinking = True
                continue
            if "...done thinking." in line:
                in_thinking = False
                continue
            
            if not in_thinking:
                yield line
