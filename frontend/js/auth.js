/**
 * Enterprise Multi-Tenant RAG Platform - Tenant Authentication Module
 * Secure, key-based tenant authentication without public self-registration.
 */

const AuthModule = {
  init() {
    this.bindEvents();
    this.renderTenantProfile();

    if (AppState.apiKey) {
      this.validateExistingSession();
    } else {
      setTimeout(() => this.openModal(), 200);
    }
  },

  bindEvents() {
    const switchBtn = document.getElementById('switch-tenant-btn');
    if (switchBtn) {
      switchBtn.addEventListener('click', () => this.openModal());
    }

    const closeBtn = document.getElementById('auth-modal-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.closeModal());
    }

    const loginForm = document.getElementById('form-existing-key');
    if (loginForm) {
      loginForm.addEventListener('submit', (e) => this.handleKeyLogin(e));
    }

    const disconnectBtn = document.getElementById('btn-disconnect-key');
    if (disconnectBtn) {
      disconnectBtn.addEventListener('click', () => this.disconnectKey());
    }
  },

  openModal() {
    const modal = document.getElementById('auth-modal');
    if (modal) modal.classList.add('active');
  },

  closeModal() {
    const modal = document.getElementById('auth-modal');
    if (modal) modal.classList.remove('active');
  },

  async validateExistingSession() {
    try {
      const docsRes = await ApiService.listDocuments();
      if (docsRes && docsRes.tenant_id) {
        if (!AppState.tenant) {
          AppState.tenant = {
            id: docsRes.tenant_id,
            name: 'Enterprise Tenant',
          };
          localStorage.setItem(CONFIG.STORAGE_KEY_TENANT, JSON.stringify(AppState.tenant));
        }
        this.renderTenantProfile();

        // Populate documents across both modules
        const docs = docsRes.documents || [];
        AppState.documents = docs;
        if (window.DocumentsModule) {
          DocumentsModule.renderDocumentList(docs);
        }
        if (window.ChatModule) {
          ChatModule.populateDocumentFilter(docs);
          ChatModule.loadConversations();
        }
      }
    } catch (err) {
      console.warn('Existing API key invalid or revoked:', err);
      showToast('Stored API Key is invalid or expired. Please sign in again.', 'warning');
      this.openModal();
    }
  },

  async handleKeyLogin(e) {
    e.preventDefault();
    const keyInput = document.getElementById('input-api-key');
    const rawKey = keyInput ? keyInput.value.trim() : '';

    if (!rawKey.startsWith('sk_live_')) {
      showToast('Invalid format. Enterprise keys must start with sk_live_', 'error');
      return;
    }

    const submitBtn = e.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = '<span class="spinner">↻</span> Validating...';
    submitBtn.disabled = true;

    try {
      AppState.apiKey = rawKey;
      const res = await ApiService.listDocuments();

      localStorage.setItem(CONFIG.STORAGE_KEY_API, rawKey);
      AppState.tenant = {
        id: res.tenant_id,
        name: 'Enterprise Tenant',
      };
      localStorage.setItem(CONFIG.STORAGE_KEY_TENANT, JSON.stringify(AppState.tenant));

      this.renderTenantProfile();
      this.closeModal();
      showToast('Signed in successfully with tenant credentials.', 'success');

      if (window.DocumentsModule) {
        DocumentsModule.fetchDocuments();
      }
      if (window.ChatModule) {
        ChatModule.loadConversations();
      }
    } catch (err) {
      AppState.apiKey = '';
      showToast(`Sign in failed: ${err.message}`, 'error');
    } finally {
      submitBtn.innerHTML = originalText;
      submitBtn.disabled = false;
    }
  },

  renderTenantProfile() {
    const orgNameEl = document.getElementById('sidebar-tenant-name');
    const keySnipEl = document.getElementById('sidebar-key-snippet');
    const headerTenantEl = document.getElementById('header-active-tenant');

    if (AppState.apiKey) {
      const snippet = `${AppState.apiKey.slice(0, 11)}...${AppState.apiKey.slice(-4)}`;
      const name = AppState.tenant?.name || 'Active Tenant';

      if (orgNameEl) orgNameEl.textContent = name;
      if (keySnipEl) keySnipEl.textContent = snippet;
      if (headerTenantEl) headerTenantEl.textContent = name;
    } else {
      if (orgNameEl) orgNameEl.textContent = 'Not Signed In';
      if (keySnipEl) keySnipEl.textContent = 'No API Key Set';
      if (headerTenantEl) headerTenantEl.textContent = 'None';
    }
  },

  disconnectKey() {
    AppState.apiKey = '';
    AppState.tenant = null;
    localStorage.removeItem(CONFIG.STORAGE_KEY_API);
    localStorage.removeItem(CONFIG.STORAGE_KEY_TENANT);
    this.renderTenantProfile();
    if (window.ChatModule) {
      ChatModule.loadConversations();
    }
    showToast('API Key disconnected.', 'info');
  },
};
