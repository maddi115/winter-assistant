"""Paginated conversation list - simple chronological display"""
from typing import List, Dict, Any, Optional
from ui.components import get_key, clear_screen

def show_conversation_list(conversations: List[Dict[str, Any]]) -> Optional[str]:
    """
    Show paginated conversation list
    
    Args:
        conversations: List of conversations (already sorted newest first)
    
    Returns:
        None: User quit
        "new": Start new conversation
        str: conversation_id to load
    """
    
    ITEMS_PER_PAGE = 13
    current_page = 0
    
    # Calculate total pages
    total_conversations = len(conversations)
    total_pages = (total_conversations + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE  # Ceiling division
    
    while True:
        clear_screen()
        print("="*60)
        print("🚀 WINTER ASSISTANT - SELECT CONVERSATION")
        print("="*60 + "\n")
        
        # Build current page options
        start_idx = current_page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, total_conversations)
        
        page_conversations = conversations[start_idx:end_idx]
        
        # Always show "New conversation" first
        options = ["🆕 New conversation"]
        conversation_ids = ["new"]
        
        # Add conversations from current page
        for conv in page_conversations:
            title = conv.get('title', 'Untitled')
            date = conv.get('last_updated', 'Unknown')
            turns = conv.get('turn_count', 0)
            
            options.append(f"📝 {title} ({date}) - {turns} turns")
            conversation_ids.append(conv['conversation_id'])
        
        # Add quit option
        options.append("❌ Quit")
        conversation_ids.append(None)
        
        # Display menu
        selected = 0
        
        while True:
            # Redraw menu
            print("\033[H\033[2J", end='')  # Clear and go to top
            print("="*60)
            print("🚀 WINTER ASSISTANT - SELECT CONVERSATION")
            print("="*60 + "\n")
            
            for i, option in enumerate(options):
                if i == selected:
                    print(f"  → {option}")
                else:
                    print(f"    {option}")
            
            print("\n" + "="*60)
            if total_pages > 1:
                print(f"Page {current_page + 1}/{total_pages} | W/S navigate | N/P page | Enter select | Q quit")
            else:
                print("W/S navigate | Enter select | Q quit")
            
            key = get_key()
            
            if key in ['w', 'W', '\x1b[A']:  # Up
                selected = (selected - 1) % len(options)
            elif key in ['s', 'S', '\x1b[B']:  # Down
                selected = (selected + 1) % len(options)
            elif key in ['n', 'N'] and total_pages > 1:  # Next page
                current_page = (current_page + 1) % total_pages
                selected = 0
                break  # Rebuild options for new page
            elif key in ['p', 'P'] and total_pages > 1:  # Previous page
                current_page = (current_page - 1) % total_pages
                selected = 0
                break  # Rebuild options for new page
            elif key in ['\r', '\n']:  # Enter
                return conversation_ids[selected]
            elif key in ['q', 'Q']:  # Quit
                return None
