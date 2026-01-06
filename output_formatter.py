import sys

class OutputFormatter:
    @staticmethod
    def clean_thinking(text):
        """Remove thinking artifacts from output"""
        if "Thinking..." in text:
            return ""
        if "...done thinking." in text:
            return ""
        return text
    
    @staticmethod
    def stream_response(generator):
        """Clean and stream AI response"""
        full_response = ""
        
        for chunk in generator:
            cleaned = OutputFormatter.clean_thinking(chunk)
            if cleaned:
                print(cleaned, end='', flush=True)
                full_response += cleaned
        
        return full_response
    
    @staticmethod
    def format_error(error_msg):
        """Format error messages cleanly"""
        return f"\n⚠️  {error_msg}\n"
    
    @staticmethod
    def format_success(msg):
        """Format success messages"""
        return f"\n✅ {msg}\n"
