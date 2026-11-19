/**
 * Enterprise Multi-Tenant RAG Platform - Toast Notification Manager
 */

function showToast(message, type = 'info', durationMs = 4000) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const iconMap = {
    success: '✓',
    error: '✕',
    warning: '⚠',
    info: 'ℹ',
  };

  toast.innerHTML = `
    <span class="toast-icon">${iconMap[type] || 'ℹ'}</span>
    <div class="toast-content" style="flex: 1; word-break: break-word;">${message}</div>
    <button class="btn-icon" style="padding: 0.1rem; font-size: 0.8rem;" aria-label="Close">✕</button>
  `;

  const closeBtn = toast.querySelector('button');
  const removeToast = () => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-10px)';
    toast.style.transition = 'all 0.2s ease';
    setTimeout(() => toast.remove(), 200);
  };

  closeBtn.addEventListener('click', removeToast);

  container.appendChild(toast);

  if (durationMs > 0) {
    setTimeout(removeToast, durationMs);
  }
}
