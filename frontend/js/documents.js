/**
 * Enterprise Multi-Tenant RAG Platform - Document Ingestion & Vault Module
 */

const DocumentsModule = {
  init() {
    this.bindEvents();
    if (AppState.apiKey) {
      this.fetchDocuments();
    }
  },

  bindEvents() {
    const dropzone = document.getElementById('doc-dropzone');
    const fileInput = document.getElementById('doc-file-input');

    if (dropzone && fileInput) {
      // Click dropzone to open file picker
      dropzone.addEventListener('click', () => fileInput.click());

      // Drag and drop events
      ['dragenter', 'dragover'].forEach((eventName) => {
        dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.add('drag-active');
        });
      });

      ['dragleave', 'drop'].forEach((eventName) => {
        dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.remove('drag-active');
        });
      });

      dropzone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files && files.length > 0) {
          this.handleFileUpload(files[0]);
        }
      });

      fileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files && files.length > 0) {
          this.handleFileUpload(files[0]);
          fileInput.value = ''; // Reset for re-uploading same file if desired
        }
      });
    }

    // Refresh Documents button
    const refreshBtn = document.getElementById('refresh-docs-btn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        this.fetchDocuments(true);
      });
    }
  },

  async handleFileUpload(file) {
    if (!AppState.apiKey) {
      showToast('Please connect an Enterprise API Key first.', 'warning');
      AuthModule.openModal();
      return;
    }

    // Validate extension
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!CONFIG.ALLOWED_EXTENSIONS.includes(ext)) {
      showToast(`Unsupported format "${ext}". Allowed: PDF, DOCX, TXT.`, 'error');
      return;
    }

    // Validate size (< 25MB)
    if (file.size > CONFIG.MAX_FILE_SIZE_BYTES) {
      showToast('File size exceeds the 25 MB enterprise limit.', 'error');
      return;
    }

    // Visual feedback on dropzone
    const dropzone = document.getElementById('doc-dropzone');
    const originalContent = dropzone.innerHTML;
    dropzone.innerHTML = `
      <div style="display: flex; flex-direction: column; align-items: center; gap: 0.75rem;">
        <span class="spinner" style="font-size: 2rem; color: var(--accent-primary);">↻</span>
        <div style="font-weight: 600;">Uploading & Ingesting "${file.name}"...</div>
        <div style="font-size: 0.8rem; color: var(--text-muted);">${(file.size / 1024).toFixed(1)} KB</div>
      </div>
    `;

    try {
      const res = await ApiService.uploadDocument(file);
      showToast(`Document "${file.name}" accepted for ingestion!`, 'success');
      
      // Immediately refresh list and kick off status polling
      await this.fetchDocuments();
      this.startStatusPolling();
    } catch (err) {
      showToast(`Upload failed: ${err.message}`, 'error');
    } finally {
      dropzone.innerHTML = originalContent;
    }
  },

  async fetchDocuments(isManual = false) {
    if (!AppState.apiKey) return;

    try {
      const res = await ApiService.listDocuments();
      const docs = res.documents || [];
      AppState.documents = docs;

      // Update badge counts in sidebar
      const badge = document.getElementById('sidebar-doc-badge');
      if (badge) {
        badge.textContent = docs.length;
      }

      this.renderDocumentList(docs);

      // Populate document filter in Chat
      if (window.ChatModule && ChatModule.populateDocumentFilter) {
        ChatModule.populateDocumentFilter(docs);
      }
      const hasActiveJobs = docs.some(
        (d) => d.upload_status === 'Pending' || d.upload_status === 'Processing'
      );

      if (hasActiveJobs) {
        this.startStatusPolling();
      } else {
        this.stopStatusPolling();
      }

      if (isManual) {
        showToast('Document list refreshed.', 'info', 2000);
      }
    } catch (err) {
      console.warn('Could not list documents:', err);
    }
  },

  renderDocumentList(docs) {
    const tbody = document.getElementById('doc-table-body');
    const emptyState = document.getElementById('doc-empty-state');
    const tableWrapper = document.getElementById('doc-table-wrapper');

    if (!tbody) return;

    if (!docs || docs.length === 0) {
      if (tableWrapper) tableWrapper.classList.add('hidden');
      if (emptyState) emptyState.classList.remove('hidden');
      tbody.innerHTML = '';
      return;
    }

    if (emptyState) emptyState.classList.add('hidden');
    if (tableWrapper) tableWrapper.classList.remove('hidden');

    // Use DocumentFragment for 60fps single-tick paint (No lag!)
    const fragment = document.createDocumentFragment();

    docs.forEach((doc) => {
      const tr = document.createElement('tr');
      tr.id = `doc-row-${doc.id}`;

      // File extension icon
      const ext = doc.filename.split('.').pop().toLowerCase();
      let icon = '📄';
      if (ext === 'pdf') icon = '📕';
      if (ext === 'docx') icon = '📘';

      // Format size
      const sizeKB = doc.file_size_bytes 
        ? (doc.file_size_bytes / 1024).toFixed(1) + ' KB'
        : 'N/A';

      // Format date
      const dateStr = doc.uploaded_at 
        ? new Date(doc.uploaded_at).toLocaleString() 
        : 'Recently';

      // Status badge markup
      const statusMarkup = this.getStatusBadgeMarkup(doc.upload_status);

      tr.innerHTML = `
        <td>
          <div class="doc-file-info">
            <span class="doc-file-icon">${icon}</span>
            <div>
              <span class="doc-filename">${escapeHtml(doc.filename)}</span>
              <span class="doc-id-sub">UUID: ${doc.id}</span>
            </div>
          </div>
        </td>
        <td>${sizeKB}</td>
        <td>${doc.chunk_count || 0} chunks</td>
        <td class="status-cell">${statusMarkup}</td>
        <td>${dateStr}</td>
        <td style="text-align: right;">
          <button class="btn btn-danger-ghost btn-sm" onclick="DocumentsModule.deleteDoc('${doc.id}', '${escapeHtml(doc.filename)}')">
            🗑 Delete
          </button>
        </td>
      `;

      fragment.appendChild(tr);
    });

    tbody.innerHTML = '';
    tbody.appendChild(fragment);
  },

  getStatusBadgeMarkup(status) {
    switch (status) {
      case 'Processed':
        return `<span class="status-badge badge-processed">✓ Processed</span>`;
      case 'Processing':
        return `<span class="status-badge badge-processing"><span class="spinner" style="font-size: 0.7rem;">↻</span> Processing</span>`;
      case 'Pending':
        return `<span class="status-badge badge-pending">⏳ Pending</span>`;
      case 'Failed':
        return `<span class="status-badge badge-failed">✕ Failed</span>`;
      default:
        return `<span class="status-badge badge-pending">${status}</span>`;
    }
  },

  startStatusPolling() {
    if (AppState.pollTimer) return;

    AppState.pollTimer = setInterval(async () => {
      try {
        const res = await ApiService.listDocuments();
        const docs = res.documents || [];
        AppState.documents = docs;

        // Surgically update existing rows in place without re-rendering the whole table
        let hasActive = false;
        docs.forEach((doc) => {
          const row = document.getElementById(`doc-row-${doc.id}`);
          if (row) {
            const statusCell = row.querySelector('.status-cell');
            if (statusCell) {
              statusCell.innerHTML = this.getStatusBadgeMarkup(doc.upload_status);
            }
          }
          if (doc.upload_status === 'Pending' || doc.upload_status === 'Processing') {
            hasActive = true;
          }
        });

        if (!hasActive) {
          this.stopStatusPolling();
          showToast('All documents have finished processing & vectorization!', 'success');
        }
      } catch (e) {
        console.warn('Polling error:', e);
      }
    }, CONFIG.DOC_POLL_INTERVAL_MS);
  },

  stopStatusPolling() {
    if (AppState.pollTimer) {
      clearInterval(AppState.pollTimer);
      AppState.pollTimer = null;
    }
  },

  async deleteDoc(documentId, filename) {
    if (!confirm(`Are you sure you want to delete "${filename}"? Chunks and embeddings will be removed.`)) {
      return;
    }

    try {
      await ApiService.deleteDocument(documentId);
      showToast(`Document "${filename}" deleted.`, 'info');
      // Remove row immediately from DOM
      const row = document.getElementById(`doc-row-${documentId}`);
      if (row) row.remove();
      // Refetch
      this.fetchDocuments();
    } catch (err) {
      showToast(`Failed to delete: ${err.message}`, 'error');
    }
  },
};

// Helper: Escape HTML to prevent injection
function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
