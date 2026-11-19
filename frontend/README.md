# Enterprise Multi-Tenant RAG Platform - Web Frontend

A production-grade, highly responsive web client built with **Modern HTML5, Vanilla CSS3, and ES6+ JavaScript**.

---

## 🌟 Key Features

1. **Enterprise Tenant Authentication**:
   - Cryptographic API Key login (`sk_live_...`).
   - Self-service "Register Organization" directly from the UI.
   - Persistent session storage (`localStorage`).
2. **Interactive RAG Query Playground**:
   - Natural language queries with Top-K parameter slider and model selection.
   - Grounded responses with **Interactive Citation Chips** (`📄 HR_Policy.pdf · 89% match · Chunk #2`).
   - **Citation Inspector Drawer**: Click any citation chip to inspect the exact source chunk snippet, document UUID, and cosine similarity score.
   - Markdown rendering with code blocks and auto-expanding prompt input.
3. **Knowledge Vault (Document Manager)**:
   - Drag-and-drop file uploader supporting `.pdf`, `.docx`, and `.txt` (up to 25 MB).
   - Real-time status badges: `Pending`, `Processing`, `Processed`, and `Failed`.
   - Automated status polling that updates row statuses in real-time.
   - Document deletion with confirmation.
4. **Responsive Across All Screen Sizes**:
   - Desktop & Laptop: Full sidebar with live health indicator.
   - Tablet & Mobile: Off-canvas slide-out drawer, touch-optimized input dock, and responsive bottom sheets.

---

## 🚀 How to Run

### Option 1: Direct Browser Launch
Simply double-click `frontend/index.html` or open it in any modern browser (Chrome, Edge, Firefox, Safari).

### Option 2: Local HTTP Server (Recommended)
From this directory, run:
```bash
python -m http.server 3000
```
Then navigate to:
```
http://127.0.0.1:3000/
```

Make sure your Django backend is running at `http://127.0.0.1:8000/`.
