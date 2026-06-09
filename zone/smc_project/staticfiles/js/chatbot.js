// Advanced AI Chatbot with Context & Smart Features
document.addEventListener('DOMContentLoaded', function() {
    const chatbotToggle = document.getElementById('chatbot-toggle');
    const chatbotWindow = document.getElementById('chatbot-window');
    const chatbotClose = document.getElementById('chatbot-close');
    const chatbotInput = document.getElementById('chatbot-input');
    const chatbotSend = document.getElementById('chatbot-send');
    const chatbotMessages = document.getElementById('chatbot-messages');
    
    // Context management
    let conversationContext = {
        lastIntent: null,
        messageCount: 0,
        startTime: new Date()
    };

    // Toggle chatbot window
    chatbotToggle.addEventListener('click', function(e) {
        e.preventDefault();
        chatbotWindow.classList.toggle('active');
        if (chatbotWindow.classList.contains('active')) {
            chatbotInput.focus();
            // Track chatbot opening
            conversationContext.messageCount = 0;
        }
    });

    // Close chatbot
    chatbotClose.addEventListener('click', function() {
        chatbotWindow.classList.remove('active');
    });

    // Send message on button click
    chatbotSend.addEventListener('click', function() {
        sendMessage();
    });

    // Send message on Enter key
    chatbotInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    // Quick reply buttons (delegated event)
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('quick-reply-btn')) {
            const message = e.target.getAttribute('data-message');
            chatbotInput.value = message;
            sendMessage();
        }
    });

    // Auto-resize input
    chatbotInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    // Function to send message with advanced features
    function sendMessage() {
        const message = chatbotInput.value.trim();
        
        if (message === '') return;

        // Add user message to chat
        addMessage(message, 'user');
        
        // Clear input
        chatbotInput.value = '';
        chatbotInput.style.height = 'auto';
        
        // Update context
        conversationContext.messageCount++;
        
        // Show typing indicator
        showTypingIndicator();
        
        // Simulate thinking delay for natural feel
        setTimeout(() => {
            // Send to backend with context
            fetch('/accounts/chatbot/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    message: message,
                    context: conversationContext
                })
            })
            .then(response => response.json())
            .then(data => {
                // Remove typing indicator
                removeTypingIndicator();
                
                // Update context
                if (data.intent) {
                    conversationContext.lastIntent = data.intent;
                }
                
                // Add bot response
                addMessage(data.response, 'bot', data.suggestions);
            })
            .catch(error => {
                console.error('Error:', error);
                removeTypingIndicator();
                addMessage('Sorry, I encountered an error. Please try again or contact support.', 'bot', ['Help', 'Contact SMC']);
            });
        }, 800); // Natural delay
    }

    // Enhanced message adding with suggestions
    function addMessage(text, sender, suggestions = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chatbot-message ${sender}-message`;
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = sender === 'bot' 
            ? '<i class="fas fa-robot"></i>' 
            : '<i class="fas fa-user"></i>';
        
        const content = document.createElement('div');
        content.className = 'message-content';
        
        const textPara = document.createElement('p');
        textPara.innerHTML = formatMessage(text);
        
        content.appendChild(textPara);
        
        // Add suggestions if provided
        if (suggestions && suggestions.length > 0) {
            const suggestionsDiv = document.createElement('div');
            suggestionsDiv.className = 'quick-replies';
            
            suggestions.forEach(suggestion => {
                const btn = document.createElement('button');
                btn.className = 'quick-reply-btn';
                btn.setAttribute('data-message', suggestion);
                btn.textContent = suggestion;
                suggestionsDiv.appendChild(btn);
            });
            
            content.appendChild(suggestionsDiv);
        }
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);
        
        chatbotMessages.appendChild(messageDiv);
        
        // Smooth scroll to bottom
        smoothScrollToBottom();
        
        // Animate message entry
        setTimeout(() => {
            messageDiv.style.opacity = '1';
            messageDiv.style.transform = 'translateY(0)';
        }, 10);
    }

    // Format message with markdown-like features
    function formatMessage(text) {
        // Convert **bold** to <strong>
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Convert newlines to <br>
        text = text.replace(/\n/g, '<br>');
        
        // Convert bullet points
        text = text.replace(/• /g, '• ');
        
        // Convert numbered lists
        text = text.replace(/(\d+)\./g, '<strong>$1.</strong>');
        
        return text;
    }

    // Enhanced typing indicator
    function showTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'chatbot-message bot-message typing-message';
        typingDiv.id = 'typing-indicator';
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = '<i class="fas fa-robot"></i>';
        
        const content = document.createElement('div');
        content.className = 'message-content';
        
        const typingIndicator = document.createElement('div');
        typingIndicator.className = 'typing-indicator';
        typingIndicator.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
        
        content.appendChild(typingIndicator);
        typingDiv.appendChild(avatar);
        typingDiv.appendChild(content);
        
        chatbotMessages.appendChild(typingDiv);
        smoothScrollToBottom();
    }

    // Remove typing indicator
    function removeTypingIndicator() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.style.opacity = '0';
            setTimeout(() => typingIndicator.remove(), 300);
        }
    }

    // Smooth scroll to bottom
    function smoothScrollToBottom() {
        chatbotMessages.scrollTo({
            top: chatbotMessages.scrollHeight,
            behavior: 'smooth'
        });
    }

    // Welcome message on first open
    let hasOpenedBefore = sessionStorage.getItem('chatbotOpened');
    chatbotToggle.addEventListener('click', function() {
        if (!hasOpenedBefore && chatbotWindow.classList.contains('active')) {
            sessionStorage.setItem('chatbotOpened', 'true');
            hasOpenedBefore = true;
        }
    });

    // Keyboard shortcut: Ctrl + / to open chatbot
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.key === '/') {
            e.preventDefault();
            chatbotWindow.classList.add('active');
            chatbotInput.focus();
        }
    });

    // Close on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && chatbotWindow.classList.contains('active')) {
            chatbotWindow.classList.remove('active');
        }
    });
});
