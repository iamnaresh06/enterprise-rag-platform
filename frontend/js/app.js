/**
 * Enterprise Multi-Tenant RAG Platform - Main Application Controller
 */

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});

const App = {
  init() {
    this.bindNavigation();
    this.bindMobileDrawer();
    this.startHealthMonitoring();

    // Initialize sub-modules
    AuthModule.init();
    DocumentsModule.init();
    ChatModule.init();

    // Pre-fetch documents on boot if already authenticated
    if (AppState.apiKey) {
      DocumentsModule.fetchDocuments();
    }
  },

  bindNavigation() {
    const navItems = document.querySelectorAll('.nav-item[data-view]');

    navItems.forEach((btn) => {
      btn.addEventListener('click', () => {
        const viewId = btn.dataset.view;
        this.switchView(viewId);
      });
    });
  },

  switchView(viewId) {
    if (viewId === 'auth') {
      AuthModule.openModal();
      return;
    }

    // Update active nav button
    document.querySelectorAll('.nav-item[data-view]').forEach((b) => {
      if (b.dataset.view === viewId) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });

    // Update visible view container
    document.querySelectorAll('.tab-view').forEach((view) => {
      view.classList.remove('active');
    });

    const targetView = document.getElementById(`view-${viewId}`);
    if (targetView) {
      targetView.classList.add('active');
      AppState.activeView = viewId;
    }

    // Close mobile drawer if open
    this.closeMobileDrawer();

    // Update header title based on active view
    const titleEl = document.getElementById('view-header-title');

    if (viewId === 'chat') {
      if (titleEl) titleEl.textContent = 'Chat';
    } else if (viewId === 'documents') {
      if (titleEl) titleEl.textContent = 'Documents';
      DocumentsModule.fetchDocuments();
    }
  },

  bindMobileDrawer() {
    const menuBtn = document.getElementById('mobile-menu-toggle');
    const sidebar = document.getElementById('app-sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');

    if (menuBtn && sidebar && backdrop) {
      menuBtn.addEventListener('click', () => {
        sidebar.classList.toggle('mobile-open');
        backdrop.classList.toggle('active');
      });

      backdrop.addEventListener('click', () => {
        this.closeMobileDrawer();
      });
    }
  },

  closeMobileDrawer() {
    const sidebar = document.getElementById('app-sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (sidebar) sidebar.classList.remove('mobile-open');
    if (backdrop) backdrop.classList.remove('active');
  },

  startHealthMonitoring() {
    const probe = async () => {
      const indicator = document.getElementById('system-health-indicator');
      const text = document.getElementById('system-health-text');

      try {
        const res = await ApiService.getHealth();
        if (res && res.status === 'healthy') {
          AppState.isSystemOnline = true;
          if (indicator) {
            indicator.classList.remove('offline');
          }
          if (text) text.textContent = 'System Online';
        } else {
          throw new Error('Unhealthy status');
        }
      } catch (e) {
        AppState.isSystemOnline = false;
        if (indicator) {
          indicator.classList.add('offline');
        }
        if (text) text.textContent = 'Backend Offline';
      }
    };

    // Immediate check + recurring interval
    probe();
    setInterval(probe, CONFIG.HEALTH_CHECK_INTERVAL_MS);
  },
};
