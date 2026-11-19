/**
 * Enterprise Multi-Tenant RAG Platform - Configuration & State Store
 */

const CONFIG = {
  // Backend API URL (defaulting to standard Django development port)
  API_BASE_URL: window.location.origin.includes('8000') 
    ? window.location.origin 
    : 'http://127.0.0.1:8000',
  
  // Storage keys
  STORAGE_KEY_API: 'enterprise_rag_api_key',
  STORAGE_KEY_TENANT: 'enterprise_rag_tenant_data',
  
  // Polling intervals
  DOC_POLL_INTERVAL_MS: 3000,
  HEALTH_CHECK_INTERVAL_MS: 15000,

  // Limits
  MAX_FILE_SIZE_BYTES: 25 * 1024 * 1024, // 25 MB
  ALLOWED_EXTENSIONS: ['.pdf', '.docx', '.txt'],
};

// Global App State (Zero overhead, direct surgical reactivity)
const AppState = {
  apiKey: localStorage.getItem(CONFIG.STORAGE_KEY_API) || '',
  tenant: null,
  activeView: 'chat',
  documents: [],
  isSystemOnline: false,
  isGenerating: false,
  pollTimer: null,
  activeCitation: null,
};

// Load saved tenant from localStorage if available
try {
  const savedTenant = localStorage.getItem(CONFIG.STORAGE_KEY_TENANT);
  if (savedTenant) {
    AppState.tenant = JSON.parse(savedTenant);
  }
} catch (e) {
  console.warn('Could not parse saved tenant:', e);
}
