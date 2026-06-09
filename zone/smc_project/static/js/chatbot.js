// Advanced AI Chatbot with Context & Smart Features
document.addEventListener('DOMContentLoaded', function() {
    const CHAT_HISTORY_KEY = 'smc_chatbot_history_v1';
    const chatbotToggle = document.getElementById('chatbot-toggle');
    const chatbotWindow = document.getElementById('chatbot-window');
    const chatbotClose = document.getElementById('chatbot-close');
    const chatbotInput = document.getElementById('chatbot-input');
    const chatbotSend = document.getElementById('chatbot-send');
    const chatbotMessages = document.getElementById('chatbot-messages');
    const chatbotMenuToggle = document.getElementById('chatbot-menu-toggle');
    const chatbotMenuDropdown = document.getElementById('chatbot-menu-dropdown');
    const chatbotViewHistory = document.getElementById('chatbot-view-history');
    const chatbotClearHistory = document.getElementById('chatbot-clear-history');
    const chatbotHistoryPanel = document.getElementById('chatbot-history-panel');
    const chatbotHistoryClose = document.getElementById('chatbot-history-close');
    const chatbotHistoryList = document.getElementById('chatbot-history-list');

    if (!chatbotToggle || !chatbotWindow || !chatbotClose || !chatbotInput || !chatbotSend || !chatbotMessages) {
        return;
    }
    
    // Context management
    let conversationContext = {
        lastIntent: null,
        messageCount: 0,
        startTime: new Date()
    };

    let chatHistory = loadHistory();

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
        closeMenu();
        closeHistoryPanel();
    });

    if (chatbotMenuToggle) {
        chatbotMenuToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            if (!chatbotMenuDropdown) return;
            chatbotMenuDropdown.classList.toggle('active');
        });
    }

    if (chatbotViewHistory) {
        chatbotViewHistory.addEventListener('click', function() {
            openHistoryPanel();
            closeMenu();
        });
    }

    if (chatbotClearHistory) {
        chatbotClearHistory.addEventListener('click', async function() {
            closeMenu();
            const shouldClear = await showPanelConfirm('Are you sure you want to clear chat history?');
            if (!shouldClear) {
                return;
            }

            chatHistory = [];
            localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory));
            renderHistory();
            showMiniNotice('Chat history cleared', 'success');
        });
    }

    if (chatbotHistoryClose) {
        chatbotHistoryClose.addEventListener('click', function() {
            closeHistoryPanel();
        });
    }

    document.addEventListener('click', function(e) {
        if (chatbotMenuDropdown && chatbotMenuDropdown.classList.contains('active')) {
            if (!chatbotMenuDropdown.contains(e.target) && e.target !== chatbotMenuToggle) {
                closeMenu();
            }
        }
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
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000);

            // Send to backend with context
            fetch('/accounts/chatbot/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                signal: controller.signal,
                body: JSON.stringify({ 
                    message: message,
                    context: conversationContext
                })
            })
            .then(response => response.json())
            .then(data => {
                clearTimeout(timeoutId);
                // Remove typing indicator
                removeTypingIndicator();
                
                // Update context
                if (data.intent) {
                    conversationContext.lastIntent = data.intent;
                }
                
                // Add bot response
                addMessage(data.response, 'bot', data.suggestions);
                persistHistory(message, data.response);
            })
            .catch(error => {
                console.error('Error:', error);
                clearTimeout(timeoutId);
                removeTypingIndicator();
                const fallback = 'I could not process that right now. Please try again, or ask a simpler question.';
                addMessage(fallback, 'bot', ['Help', 'Submit Complaint', 'Contact SMC']);
                persistHistory(message, fallback);
            });
        }, 800); // Natural delay
    }

    function loadHistory() {
        try {
            const raw = localStorage.getItem(CHAT_HISTORY_KEY);
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            return [];
        }
    }

    function persistHistory(userMessage, botResponse) {
        const entry = {
            user: userMessage,
            bot: botResponse,
            at: new Date().toISOString()
        };

        chatHistory.push(entry);
        if (chatHistory.length > 30) {
            chatHistory = chatHistory.slice(chatHistory.length - 30);
        }

        localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory));
        renderHistory();
    }

    function openHistoryPanel() {
        if (!chatbotHistoryPanel) return;
        renderHistory();
        chatbotHistoryPanel.classList.add('active');
        chatbotHistoryPanel.setAttribute('aria-hidden', 'false');
        chatbotWindow.classList.add('history-mode');
    }

    function closeHistoryPanel() {
        if (!chatbotHistoryPanel) return;
        chatbotHistoryPanel.classList.remove('active');
        chatbotHistoryPanel.setAttribute('aria-hidden', 'true');
        chatbotWindow.classList.remove('history-mode');
    }

    function closeMenu() {
        if (chatbotMenuDropdown) {
            chatbotMenuDropdown.classList.remove('active');
        }
    }

    function showMiniNotice(message, type = 'success') {
        if (!chatbotWindow) return;

        const notice = document.createElement('div');
        notice.className = `chatbot-mini-notice ${type}`;
        notice.textContent = message;
        chatbotWindow.appendChild(notice);

        setTimeout(() => {
            notice.classList.add('show');
        }, 20);

        setTimeout(() => {
            notice.classList.remove('show');
            setTimeout(() => notice.remove(), 220);
        }, 1600);
    }

    function showPanelConfirm(message) {
        if (!chatbotWindow) {
            return Promise.resolve(false);
        }

        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'chatbot-confirm-overlay';

            const box = document.createElement('div');
            box.className = 'chatbot-confirm-box';
            box.innerHTML = `
                <div class="chatbot-confirm-title">Confirm Action</div>
                <div class="chatbot-confirm-text"></div>
                <div class="chatbot-confirm-actions">
                    <button type="button" class="chatbot-confirm-btn chatbot-confirm-cancel">No</button>
                    <button type="button" class="chatbot-confirm-btn chatbot-confirm-yes">Yes</button>
                </div>
            `;

            box.querySelector('.chatbot-confirm-text').textContent = message;
            overlay.appendChild(box);
            chatbotWindow.appendChild(overlay);

            const cancelBtn = box.querySelector('.chatbot-confirm-cancel');
            const yesBtn = box.querySelector('.chatbot-confirm-yes');

            const close = (result) => {
                overlay.remove();
                resolve(result);
            };

            cancelBtn.addEventListener('click', function() {
                close(false);
            });

            yesBtn.addEventListener('click', function() {
                close(true);
            });

            overlay.addEventListener('click', function(e) {
                if (e.target === overlay) {
                    close(false);
                }
            });
        });
    }

    function renderHistory() {
        if (!chatbotHistoryList) return;

        if (!chatHistory.length) {
            chatbotHistoryList.innerHTML = '<div class="chatbot-history-empty">No chat history yet.</div>';
            return;
        }

        const items = chatHistory
            .slice()
            .reverse()
            .map((item) => {
                const dt = new Date(item.at);
                const time = isNaN(dt.getTime()) ? '' : dt.toLocaleString();
                return `
                    <div class="chatbot-history-item">
                        <span class="history-time">${escapeHtml(time)}</span>
                        <strong>You:</strong> ${escapeHtml(item.user || '')}<br>
                        <strong>Bot:</strong> ${escapeHtml((item.bot || '').slice(0, 180))}
                    </div>
                `;
            })
            .join('');

        chatbotHistoryList.innerHTML = items;
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
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

    renderHistory();

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
