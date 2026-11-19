/**
 * Enterprise Multi-Tenant RAG Platform - API Client Service
 */

const ApiService = {
  /**
   * Universal fetch wrapper with automatic tenant key injection and error normalisation.
   */
  async request(endpoint, options = {}) {
    const url = `${CONFIG.API_BASE_URL}${endpoint}`;
    const headers = options.headers || {};

    // Automatically inject Tenant API Key if present
    if (AppState.apiKey && !headers['X-API-Key']) {
      headers['X-API-Key'] = AppState.apiKey;
    }

    // Default to JSON Content-Type unless FormData is passed
    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      // Handle 204 No Content
      if (response.status === 204) {
        return { success: true };
      }

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        let errorMsg = data?.error?.message 
          || data?.detail 
          || data?.message;

        // Extract DRF field validation errors like {"file": ["..."]}
        if (!errorMsg && typeof data === 'object' && data !== null) {
          const firstKey = Object.keys(data)[0];
          if (firstKey) {
            const val = data[firstKey];
            errorMsg = Array.isArray(val) ? `${firstKey}: ${val[0]}` : `${firstKey}: ${val}`;
          }
        }

        if (!errorMsg) {
          errorMsg = `Request failed with HTTP status ${response.status}`;
        }
        throw new Error(errorMsg);
      }

      return data;
    } catch (err) {
      console.error(`API Error [${endpoint}]:`, err);
      throw err;
    }
  },

  // Health Probe
  async getHealth() {
    return this.request('/api/v1/health/');
  },

  // Tenant Registration
  async registerTenant(orgName, keyName = 'Primary Production Key') {
    return this.request('/api/v1/auth/tenants/', {
      method: 'POST',
      body: JSON.stringify({
        name: orgName,
        key_name: keyName,
      }),
    });
  },

  // Validate Active Key
  async listKeys() {
    return this.request('/api/v1/auth/keys/', {
      method: 'GET',
    });
  },

  // Upload Document
  async uploadDocument(file) {
    const formData = new FormData();
    formData.append('file', file);

    return this.request('/api/v1/documents/upload/', {
      method: 'POST',
      headers: {
        // Leave Content-Type empty so browser sets multipart boundary automatically
      },
      body: formData,
    });
  },

  // List Documents for Tenant
  async listDocuments() {
    return this.request('/api/v1/documents/', {
      method: 'GET',
    });
  },

  // Delete Document
  async deleteDocument(documentId) {
    return this.request(`/api/v1/documents/${documentId}/`, {
      method: 'DELETE',
    });
  },

  // Submit RAG Query
  async submitQuery(queryText, topK = 4, documentId = null) {
    const payload = {
      query: queryText,
      top_k: parseInt(topK, 10) || 4,
    };
    if (documentId) {
      payload.document_id = documentId;
    }
    return this.request('/api/v1/query/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};
