from django.contrib.messages import get_messages
from django.contrib import messages


class UsernameLoginMessageMiddleware:
    """Middleware to replace allauth's email-based login message with username."""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Check if user is authenticated in this response
        if request.user.is_authenticated:
            # Get message storage
            storage = get_messages(request)
            
            # Find and replace the allauth login message
            messages_to_process = []
            found_login_message = False
            
            for message in storage:
                msg_text = str(message)
                # Check if this is the allauth login message
                if "Successfully signed in as" in msg_text and "@" in msg_text:
                    found_login_message = True
                    messages_to_process.append({
                        'type': 'login',
                        'level': message.level,
                        'user': request.user
                    })
                else:
                    messages_to_process.append({
                        'type': 'other',
                        'text': msg_text,
                        'level': message.level
                    })
            
            # If we found a login message, rebuild the messages
            if found_login_message:
                # Force used to discard current messages
                storage.used = True
                
                # Re-add messages with the corrected login message
                for msg_data in messages_to_process:
                    if msg_data['type'] == 'login':
                        messages.success(request, f"Successfully signed in as {msg_data['user'].username}.")
                    else:
                        messages.add_message(request, msg_data['level'], msg_data['text'])
        
        return response
