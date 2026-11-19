/**
 * Enterprise Multi-Tenant RAG Platform - Clean Multi-Chat & Citation Module
 * Supports Gemini/ChatGPT-style sidebar conversation threads, global or single-document
 * scoped queries, direct file uploads from the prompt dock, and verified citation modals.
 */

const ChatModule = {
  conversations: [],
  activeConversationId: null,
  selectedDocId: '',
  selectedDocName: '',

  init() {
    this.bindEvents();
    this.setupAutoExpandingTextarea();
    this.loadConversations();
  },

  getStorageKey() {
    const tenantId = AppState.tenant?.id || 'active_tenant';
    return `enterprise_rag_threads_${tenantId}`;
  },

  bindEvents() {
    const form = document.getElementById('chat-prompt-form');
    const textarea = document.getElementById('prompt-input');
    const clearBtn = document.getElementById('clear-chat-btn');
    const newChatBtn = document.getElementById('btn-new-chat');
    const plusBtn = document.getElementById('prompt-select-doc-btn');
    const docSelect = document.getElementById('chat-doc-filter-select');
    const popover = document.getElementById('doc-picker-popover');
    const popoverClose = document.getElementById('doc-picker-close-btn');
    const uploadBtn = document.getElementById('doc-picker-upload-btn');
    const directFileInput = document.getElementById('chat-direct-file-input');
    const scopeClearBtn = document.getElementById('prompt-scope-clear-btn');

    // Prompt Form Submit
    if (form) {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        this.submitPrompt();
      });
    }

    // Enter to submit (Shift+Enter for newline)
    if (textarea) {
      textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this.submitPrompt();
        }
      });
    }

    // Clear active conversation
    if (clearBtn) {
      clearBtn.addEventListener('click', () => this.clearActiveChat());
    }

    // New Chat Button (+ New Chat in sidebar)
    if (newChatBtn) {
      newChatBtn.addEventListener('click', () => {
        this.createNewConversation(true);
      });
    }

    // Plus (+) button to toggle document selection popover
    if (plusBtn) {
      plusBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.toggleDocPicker();
      });
    }

    // Close Popover button
    if (popoverClose) {
      popoverClose.addEventListener('click', (e) => {
        e.stopPropagation();
        this.closeDocPicker();
      });
    }

    // Direct Upload Button inside popover
    if (uploadBtn && directFileInput) {
      uploadBtn.addEventListener('click', (e) => {
        e.preventDefault();
        this.closeDocPicker();
        directFileInput.click();
      });
    }

    // Direct File Input Change
    if (directFileInput) {
      directFileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files && files.length > 0) {
          this.handleDirectDocUpload(files[0]);
          directFileInput.value = '';
        }
      });
    }

    // Scope Pill Clear (x) button
    if (scopeClearBtn) {
      scopeClearBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.setScope('', 'All Uploaded Documents');
      });
    }

    // Close popover when clicking anywhere outside
    document.addEventListener('click', (e) => {
      if (popover && !popover.classList.contains('hidden') && !popover.contains(e.target) && e.target !== plusBtn) {
        this.closeDocPicker();
      }
    });

    // Top Header Document Scope Selector Change
    if (docSelect) {
      docSelect.addEventListener('change', () => {
        const docId = docSelect.value;
        const docName = docSelect.options[docSelect.selectedIndex]?.text || '';
        this.setScope(docId, docName);
      });
    }

    // Suggestion chips
    document.querySelectorAll('.suggestion-card').forEach((card) => {
      card.addEventListener('click', () => {
        const promptText = card.dataset.prompt;
        if (promptText && textarea) {
          textarea.value = promptText;
          this.submitPrompt();
        }
      });
    });

    // Close Citation Modal
    const citationModalClose = document.getElementById('citation-modal-close');
    if (citationModalClose) {
      citationModalClose.addEventListener('click', () => this.closeCitationModal());
    }

    // Copy Citation Snippet
    const copySnippetBtn = document.getElementById('copy-citation-snippet-btn');
    if (copySnippetBtn) {
      copySnippetBtn.addEventListener('click', () => {
        const snippetText = document.getElementById('citation-snippet-content')?.textContent;
        if (snippetText) {
          navigator.clipboard.writeText(snippetText);
          showToast('Citation snippet copied to clipboard!', 'success');
        }
      });
    }
  },

  // ==========================================
  // MULTI-CHAT CONVERSATION THREAD MANAGEMENT
  // ==========================================

  loadConversations() {
    try {
      const key = this.getStorageKey();
      const raw = localStorage.getItem(key);
      let parsed = [];

      if (raw) {
        try {
          parsed = JSON.parse(raw);
        } catch (e) {
          console.warn('Could not parse conversations:', e);
        }
      }

      // Check legacy single-chat migration
      if (!Array.isArray(parsed) || parsed.length === 0) {
        const tenantId = AppState.tenant?.id || 'active_tenant';
        const legacyKey = `enterprise_rag_chat_${tenantId}`;
        const legacyRaw = localStorage.getItem(legacyKey);
        if (legacyRaw) {
          try {
            const legacyItems = JSON.parse(legacyRaw);
            if (Array.isArray(legacyItems) && legacyItems.length > 0) {
              const firstUserMsg = legacyItems.find((m) => m.type === 'user');
              const initialTitle = firstUserMsg ? this.formatConversationTitle(firstUserMsg.text) : 'Previous Conversation';
              parsed = [
                {
                  id: `conv_${Date.now()}`,
                  title: initialTitle,
                  selectedDocId: '',
                  selectedDocName: '',
                  createdAt: Date.now(),
                  updatedAt: Date.now(),
                  messages: legacyItems,
                },
              ];
            }
          } catch (e) {}
        }
      }

      if (Array.isArray(parsed) && parsed.length > 0) {
        parsed.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
        this.conversations = parsed;
        this.activeConversationId = parsed[0].id;
      } else {
        this.createNewConversation(false);
        return;
      }

      this.renderSidebarConversations();
      this.loadActiveConversation();
    } catch (e) {
      console.warn('Error loading conversations:', e);
      this.createNewConversation(false);
    }
  },

  saveConversations() {
    try {
      const key = this.getStorageKey();
      localStorage.setItem(key, JSON.stringify(this.conversations));
      this.renderSidebarConversations();
    } catch (e) {
      console.warn('Could not persist conversations:', e);
    }
  },

  createNewConversation(focusInput = true) {
    const newId = `conv_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
    const newConv = {
      id: newId,
      title: 'New Chat',
      selectedDocId: this.selectedDocId || '',
      selectedDocName: this.selectedDocName || '',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [],
    };

    this.conversations.unshift(newConv);
    this.activeConversationId = newId;
    this.saveConversations();
    this.loadActiveConversation();

    if (focusInput) {
      const input = document.getElementById('prompt-input');
      if (input) input.focus();
      if (window.App && App.closeMobileDrawer) {
        App.closeMobileDrawer();
      }
      if (AppState.activeView !== 'chat' && window.App && App.switchView) {
        App.switchView('chat');
      }
    }
  },

  selectConversation(convId) {
    if (this.activeConversationId === convId) return;

    const conv = this.conversations.find((c) => c.id === convId);
    if (!conv) return;

    this.activeConversationId = convId;
    this.setScope(conv.selectedDocId || '', conv.selectedDocName || '', false);
    this.loadActiveConversation();
    this.renderSidebarConversations();

    if (window.App && App.closeMobileDrawer) {
      App.closeMobileDrawer();
    }
    if (AppState.activeView !== 'chat' && window.App && App.switchView) {
      App.switchView('chat');
    }
  },

  deleteConversation(convId, e) {
    if (e) e.stopPropagation();

    this.conversations = this.conversations.filter((c) => c.id !== convId);

    if (this.activeConversationId === convId) {
      if (this.conversations.length > 0) {
        this.selectConversation(this.conversations[0].id);
      } else {
        this.createNewConversation(false);
      }
    } else {
      this.saveConversations();
    }

    showToast('Conversation deleted.', 'info', 1500);
  },

  renderSidebarConversations() {
    const listEl = document.getElementById('sidebar-chat-list');
    const badgeEl = document.getElementById('sidebar-chat-count');

    if (badgeEl) {
      badgeEl.textContent = this.conversations.length;
    }

    if (!listEl) return;
    listEl.innerHTML = '';

    if (this.conversations.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.style.cssText = 'padding: 0.65rem 0.5rem; font-size: 0.75rem; color: var(--text-muted); text-align: center;';
      emptyDiv.textContent = 'No chats yet';
      listEl.appendChild(emptyDiv);
      return;
    }

    this.conversations.forEach((conv) => {
      const item = document.createElement('div');
      item.className = `chat-history-item ${conv.id === this.activeConversationId ? 'active' : ''}`;
      item.dataset.convId = conv.id;

      item.innerHTML = `
        <div class="item-content">
          <span class="item-icon">💬</span>
          <span class="item-title" title="${escapeHtml(conv.title)}">${escapeHtml(conv.title)}</span>
        </div>
        <button type="button" class="item-delete-btn" title="Delete conversation">✕</button>
      `;

      item.addEventListener('click', () => {
        this.selectConversation(conv.id);
      });

      const delBtn = item.querySelector('.item-delete-btn');
      if (delBtn) {
        delBtn.addEventListener('click', (e) => {
          this.deleteConversation(conv.id, e);
        });
      }

      listEl.appendChild(item);
    });
  },

  loadActiveConversation() {
    const stream = document.getElementById('chat-stream-inner');
    const emptyState = document.getElementById('chat-empty-state');
    if (!stream) return;

    stream.innerHTML = '';

    const currentConv = this.conversations.find((c) => c.id === this.activeConversationId);
    if (!currentConv || !currentConv.messages || currentConv.messages.length === 0) {
      if (emptyState) {
        stream.appendChild(emptyState);
        emptyState.classList.remove('hidden');
      }
      return;
    }

    if (emptyState) emptyState.classList.add('hidden');

    currentConv.messages.forEach((msg, idx) => {
      if (msg.type === 'user') {
        this.appendUserMessage(msg.text, msg.docName);
      } else if (msg.type === 'agent') {
        this.appendAgentMessage(msg.answer, msg.citations || [], msg.meta || {}, idx);
      }
    });

    this.scrollToBottom();
  },

  clearActiveChat() {
    const currentConv = this.conversations.find((c) => c.id === this.activeConversationId);
    if (currentConv) {
      currentConv.messages = [];
      currentConv.title = 'New Chat';
      currentConv.updatedAt = Date.now();
      this.saveConversations();
    }
    this.loadActiveConversation();
    showToast('Conversation cleared.', 'info', 1500);
  },

  formatConversationTitle(prompt) {
    if (!prompt) return 'New Chat';
    let clean = prompt.trim();
    clean = clean.replace(/^(what is|what was|tell me about|summarize|who is|who was|can you describe|explain)\s+/i, '');
    clean = clean.replace(/[?.,!]+$/, '').trim();
    if (!clean) clean = prompt.trim();
    if (clean.length > 32) {
      clean = clean.substring(0, 30) + '...';
    }
    return clean.charAt(0).toUpperCase() + clean.slice(1);
  },

  // ==========================================
  // DOCUMENT FILTER & SCOPING LOGIC
  // ==========================================

  setScope(docId, docName, syncConv = true) {
    this.selectedDocId = docId || '';
    this.selectedDocName = docName || '';

    // 1. Sync the top Header select dropdown
    const select = document.getElementById('chat-doc-filter-select');
    if (select) {
      select.value = this.selectedDocId;
    }

    // 2. Sync Scope Badge Indicator Pill
    const badge = document.getElementById('prompt-scope-badge');
    const badgeName = document.getElementById('prompt-scope-name');

    if (this.selectedDocId) {
      if (badge) badge.classList.remove('hidden');
      if (badgeName) badgeName.textContent = this.selectedDocName.replace(/^📄\s*/, '');
      showToast(`Search filtered to: ${this.selectedDocName.replace(/^📄\s*/, '')}`, 'info', 2000);
    } else {
      if (badge) badge.classList.add('hidden');
      if (syncConv) showToast('Searching all uploaded documents.', 'info', 1800);
    }

    // 3. Update active state in Popover list
    const pickerItems = document.querySelectorAll('.doc-picker-item');
    pickerItems.forEach((btn) => {
      if (btn.dataset.docId === this.selectedDocId) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // 4. Persist to active conversation
    if (syncConv) {
      const currentConv = this.conversations.find((c) => c.id === this.activeConversationId);
      if (currentConv) {
        currentConv.selectedDocId = this.selectedDocId;
        currentConv.selectedDocName = this.selectedDocName;
        this.saveConversations();
      }
    }

    this.closeDocPicker();
  },

  populateDocumentFilter(docs) {
    const select = document.getElementById('chat-doc-filter-select');
    const pickerList = document.getElementById('doc-picker-list');

    // 1. Populate top Header Select dropdown
    if (select) {
      const currentVal = this.selectedDocId || select.value;
      select.innerHTML = '<option value="">All Uploaded Documents</option>';
      if (docs && docs.length > 0) {
        docs.forEach((d) => {
          const opt = document.createElement('option');
          opt.value = d.id;
          opt.textContent = `📄 ${d.filename} (${d.chunk_count || 0} chunks)`;
          if (d.id === currentVal) opt.selected = true;
          select.appendChild(opt);
        });
      }
    }

    // 2. Populate Document Popover List
    if (pickerList) {
      pickerList.innerHTML = '';

      // Global option
      const globalBtn = document.createElement('button');
      globalBtn.type = 'button';
      globalBtn.className = `doc-picker-item ${!this.selectedDocId ? 'active' : ''}`;
      globalBtn.dataset.docId = '';
      globalBtn.innerHTML = `
        <span class="item-icon">🌐</span>
        <div class="item-info">
          <span class="item-title">All Uploaded Documents</span>
          <span class="item-subtitle">Global semantic search across tenant vault</span>
        </div>
      `;
      globalBtn.addEventListener('click', () => {
        this.setScope('', 'All Uploaded Documents');
      });
      pickerList.appendChild(globalBtn);

      // Individual Document options
      if (docs && docs.length > 0) {
        docs.forEach((d) => {
          const docBtn = document.createElement('button');
          docBtn.type = 'button';
          docBtn.className = `doc-picker-item ${this.selectedDocId === d.id ? 'active' : ''}`;
          docBtn.dataset.docId = d.id;
          docBtn.dataset.docName = d.filename;
          docBtn.innerHTML = `
            <span class="item-icon">📄</span>
            <div class="item-info">
              <span class="item-title">${escapeHtml(d.filename)}</span>
              <span class="item-subtitle">${d.chunk_count || 0} chunks · ${d.upload_status || 'Ready'}</span>
            </div>
          `;
          docBtn.addEventListener('click', () => {
            this.setScope(d.id, d.filename);
          });
          pickerList.appendChild(docBtn);
        });
      } else {
        const emptyHint = document.createElement('div');
        emptyHint.style.cssText = 'padding: 0.75rem 0.5rem; font-size: 0.76rem; color: var(--text-muted); text-align: center;';
        emptyHint.textContent = 'No indexed documents found in vault.';
        pickerList.appendChild(emptyHint);
      }
    }
  },

  async toggleDocPicker() {
    const popover = document.getElementById('doc-picker-popover');
    if (!popover) return;

    if (popover.classList.contains('hidden')) {
      // Re-populate with current AppState
      this.populateDocumentFilter(AppState.documents || []);

      // If documents haven't loaded yet, fetch them
      if (!AppState.documents || AppState.documents.length === 0) {
        if (window.DocumentsModule && DocumentsModule.fetchDocuments) {
          await DocumentsModule.fetchDocuments();
          this.populateDocumentFilter(AppState.documents || []);
        }
      }
      popover.classList.remove('hidden');
    } else {
      popover.classList.add('hidden');
    }
  },

  closeDocPicker() {
    const popover = document.getElementById('doc-picker-popover');
    if (popover) popover.classList.add('hidden');
  },

  async handleDirectDocUpload(file) {
    if (!AppState.apiKey) {
      showToast('Please sign in with a Tenant API Key first.', 'warning');
      AuthModule.openModal();
      return;
    }

    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!CONFIG.ALLOWED_EXTENSIONS.includes(ext)) {
      showToast(`Unsupported format "${ext}". Allowed: PDF, DOCX, TXT.`, 'error');
      return;
    }

    if (file.size > CONFIG.MAX_FILE_SIZE_BYTES) {
      showToast('File size exceeds the 25 MB enterprise limit.', 'error');
      return;
    }

    const statusPill = document.getElementById('prompt-upload-status');
    const statusText = document.getElementById('prompt-upload-status-text');

    if (statusPill) statusPill.classList.remove('hidden');
    if (statusText) statusText.textContent = `Uploading "${file.name}"...`;
    showToast(`Uploading "${file.name}" to knowledge vault...`, 'info', 2500);

    try {
      const uploadRes = await ApiService.uploadDocument(file);
      if (statusText) statusText.textContent = `Vectorizing "${file.name}"...`;

      // Poll until processed
      let attempts = 0;
      let isReady = false;
      let matchedDoc = null;

      while (attempts < 15 && !isReady) {
        await new Promise((r) => setTimeout(r, 1200));
        attempts++;
        try {
          const res = await ApiService.listDocuments();
          const docs = res.documents || [];
          AppState.documents = docs;
          matchedDoc = docs.find((d) => d.id === uploadRes.id || d.filename === file.name);
          if (matchedDoc && matchedDoc.upload_status === 'Processed') {
            isReady = true;
          }
        } catch (e) {}
      }

      // Refresh documents across both modules
      if (window.DocumentsModule && DocumentsModule.fetchDocuments) {
        await DocumentsModule.fetchDocuments();
      }

      // Automatically select newly uploaded document for search!
      if (matchedDoc) {
        this.setScope(matchedDoc.id, matchedDoc.filename, true);
        showToast(`Document "${file.name}" ready! Search scope set to this document.`, 'success', 3500);
      } else {
        showToast(`Document "${file.name}" uploaded to vault!`, 'success', 3000);
      }
    } catch (err) {
      showToast(`Upload failed: ${err.message}`, 'error');
    } finally {
      if (statusPill) statusPill.classList.add('hidden');
    }
  },

  // ==========================================
  // CHAT STREAM & QUERY EXECUTION
  // ==========================================

  setupAutoExpandingTextarea() {
    const textarea = document.getElementById('prompt-input');
    if (!textarea) return;

    textarea.addEventListener('input', () => {
      textarea.style.height = 'auto';
      const newHeight = Math.min(textarea.scrollHeight, 150);
      textarea.style.height = `${newHeight}px`;
    });
  },

  async submitPrompt() {
    if (AppState.isGenerating) return;

    const textarea = document.getElementById('prompt-input');
    const promptText = textarea ? textarea.value.trim() : '';

    if (!promptText) return;

    if (!AppState.apiKey) {
      showToast('Please sign in with a Tenant API Key to query.', 'warning');
      AuthModule.openModal();
      return;
    }

    // Hide empty state
    const emptyState = document.getElementById('chat-empty-state');
    if (emptyState) emptyState.classList.add('hidden');

    const selectedDocId = this.selectedDocId || null;
    const selectedDocName = this.selectedDocId ? this.selectedDocName : null;

    // Get current active conversation
    let currentConv = this.conversations.find((c) => c.id === this.activeConversationId);
    if (!currentConv) {
      this.createNewConversation(false);
      currentConv = this.conversations[0];
    }

    // Auto-generate title if this is the first prompt in the conversation
    if (currentConv.messages.length === 0 || currentConv.title === 'New Chat') {
      currentConv.title = this.formatConversationTitle(promptText);
    }

    // 1. Append User Message to UI & conversation state
    this.appendUserMessage(promptText, selectedDocName);
    currentConv.messages.push({
      type: 'user',
      text: promptText,
      docName: selectedDocName,
      timestamp: Date.now(),
    });
    currentConv.updatedAt = Date.now();

    // Reorder conversation to top of list
    this.conversations = [
      currentConv,
      ...this.conversations.filter((c) => c.id !== currentConv.id),
    ];
    this.saveConversations();

    textarea.value = '';
    textarea.style.height = 'auto';

    // 2. Append Thinking Pulse State
    const thinkingRowId = this.appendThinkingState();

    // 3. Dispatch Query to RAG Backend
    AppState.isGenerating = true;
    const startTime = performance.now();

    try {
      const response = await ApiService.submitQuery(promptText, 4, selectedDocId);
      const latencyMs = response.latency_ms || Math.round(performance.now() - startTime);

      // Remove thinking animation
      const thinkingEl = document.getElementById(thinkingRowId);
      if (thinkingEl) thinkingEl.remove();

      const meta = {
        latencyMs,
        retrievedCount: response.retrieved_chunk_count || (response.citations ? response.citations.length : 0),
        tenantId: response.tenant_id,
        targetDoc: selectedDocName,
      };

      const msgIndex = currentConv.messages.length;

      // 4. Render Agent Response with Grounded Citations
      this.appendAgentMessage(response.answer, response.citations || [], meta, msgIndex);

      currentConv.messages.push({
        type: 'agent',
        answer: response.answer,
        citations: response.citations || [],
        meta: meta,
        timestamp: Date.now(),
      });
      currentConv.updatedAt = Date.now();
      this.saveConversations();
    } catch (err) {
      const thinkingEl = document.getElementById(thinkingRowId);
      if (thinkingEl) thinkingEl.remove();

      const errMeta = { latencyMs: Math.round(performance.now() - startTime), isError: true };
      const errMsg = `Error querying RAG engine: ${err.message}`;

      this.appendAgentMessage(errMsg, [], errMeta, currentConv.messages.length);

      currentConv.messages.push({
        type: 'agent',
        answer: errMsg,
        citations: [],
        meta: errMeta,
        timestamp: Date.now(),
      });
      currentConv.updatedAt = Date.now();
      this.saveConversations();

      showToast(err.message, 'error');
    } finally {
      AppState.isGenerating = false;
      this.scrollToBottom();
    }
  },

  appendUserMessage(text, docFilterName = null) {
    const stream = document.getElementById('chat-stream-inner');
    if (!stream) return;

    const filterTag = docFilterName
      ? `<div style="font-size: 0.72rem; color: var(--text-muted); margin-bottom: 0.25rem;">🔍 Scoped to: ${escapeHtml(docFilterName)}</div>`
      : '';

    const row = document.createElement('div');
    row.className = 'message-row user';
    row.innerHTML = `
      <div class="message-bubble">
        ${filterTag}
        ${escapeHtml(text)}
      </div>
    `;

    stream.appendChild(row);
    this.scrollToBottom();
  },

  appendThinkingState() {
    const stream = document.getElementById('chat-stream-inner');
    const rowId = `thinking-${Date.now()}`;

    const row = document.createElement('div');
    row.id = rowId;
    row.className = 'message-row agent';
    row.innerHTML = `
      <div class="message-avatar">AI</div>
      <div class="message-bubble">
        <div class="agent-thinking">
          <div class="thinking-dot"></div>
          <span class="thinking-text">Searching indexed documents & synthesizing response...</span>
        </div>
      </div>
    `;

    stream.appendChild(row);
    this.scrollToBottom();
    return rowId;
  },

  appendAgentMessage(answer, citations = [], meta = {}, messageIndex = 0) {
    const stream = document.getElementById('chat-stream-inner');
    if (!stream) return;

    const formattedAnswer = this.formatMarkdown(answer);
    const row = document.createElement('div');
    row.className = 'message-row agent';

    // Citation Chips Markup
    let citationsMarkup = '';
    if (citations && citations.length > 0) {
      const chipsHtml = citations
        .map((cit, idx) => {
          const scorePercent = cit.similarity_score
            ? `${(cit.similarity_score * 100).toFixed(1)}%`
            : 'Match';

          return `
            <button type="button" class="citation-chip" onclick="ChatModule.openCitationModalByIndex(${messageIndex}, ${idx})" title="Click to view verified source chunk">
              <span class="chip-icon">📄</span>
              <span class="chip-filename">${escapeHtml(cit.filename || 'Document')}</span>
              <span class="chip-score">${scorePercent}</span>
              <span style="font-size: 0.68rem; color: var(--text-muted);">#${cit.chunk_index ?? 0}</span>
            </button>
          `;
        })
        .join('');

      citationsMarkup = `
        <div class="citations-section">
          <div class="citations-header">
            <span>Verified Citations (${citations.length})</span>
          </div>
          <div class="citations-chips-container">
            ${chipsHtml}
          </div>
        </div>
      `;
    }

    row.innerHTML = `
      <div class="message-avatar">AI</div>
      <div class="message-bubble">
        <div class="agent-text-content">
          ${formattedAnswer}
        </div>
        ${citationsMarkup}
        <div class="message-meta-bar">
          <span class="latency-pill">
            ⚡ ${meta.latencyMs || 0}ms · ${meta.retrievedCount || 0} chunks
          </span>
          <button type="button" class="btn-icon" onclick="ChatModule.copyAnswer(this)" title="Copy Answer" style="font-size: 0.74rem;">
            Copy
          </button>
        </div>
      </div>
    `;

    stream.appendChild(row);
    this.scrollToBottom();
  },

  openCitationModalByIndex(messageIndex, citationIndex) {
    const currentConv = this.conversations.find((c) => c.id === this.activeConversationId);
    if (!currentConv || !currentConv.messages) return;

    const msg = currentConv.messages[messageIndex];
    if (!msg || !msg.citations || !msg.citations[citationIndex]) return;

    const cit = msg.citations[citationIndex];
    const modal = document.getElementById('citation-modal');
    const titleEl = document.getElementById('citation-modal-filename');
    const docIdEl = document.getElementById('citation-modal-docid');
    const chunkIdxEl = document.getElementById('citation-modal-chunkidx');
    const scoreEl = document.getElementById('citation-modal-score');
    const snippetEl = document.getElementById('citation-snippet-content');

    if (titleEl) titleEl.textContent = cit.filename || 'Document';
    if (docIdEl) docIdEl.textContent = cit.document_id || 'N/A';
    if (chunkIdxEl) chunkIdxEl.textContent = cit.chunk_index ?? 0;
    if (scoreEl) {
      scoreEl.textContent = cit.similarity_score
        ? `${(cit.similarity_score * 100).toFixed(1)}% Match`
        : 'Relevant';
    }
    if (snippetEl) snippetEl.textContent = cit.snippet || 'No raw snippet captured.';

    if (modal) modal.classList.add('active');
  },

  closeCitationModal() {
    const modal = document.getElementById('citation-modal');
    if (modal) modal.classList.remove('active');
  },

  copyAnswer(buttonEl) {
    const bubble = buttonEl.closest('.message-bubble');
    const content = bubble ? bubble.querySelector('.agent-text-content')?.innerText : '';
    if (content) {
      navigator.clipboard.writeText(content);
      showToast('Answer copied to clipboard.', 'info', 1500);
    }
  },

  scrollToBottom() {
    const stream = document.getElementById('chat-stream');
    if (stream) {
      stream.scrollTop = stream.scrollHeight;
    }
  },

  formatMarkdown(rawText) {
    if (!rawText) return '';

    let text = escapeHtml(rawText);

    // Code blocks & inline code
    text = text.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Headings
    text = text.replace(/^#### (.*?)$/gm, '<h4>$1</h4>');
    text = text.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
    text = text.replace(/^## (.*?)$/gm, '<h2>$1</h2>');

    // Bold & italic
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Bullet points
    text = text.replace(/(?:^|\n)[-*]\s+(.+)/g, '<li>$1</li>');
    text = text.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');

    const paragraphs = text
      .split(/\n\n+/)
      .map((p) => (p.startsWith('<ul>') || p.startsWith('<pre>') || p.startsWith('<h') ? p : `<p>${p.replace(/\n/g, '<br/>')}</p>`))
      .join('');

    return paragraphs;
  },
};
