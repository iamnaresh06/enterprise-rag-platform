import time
import logging
import requests
from typing import Dict, Any, List
from django.conf import settings
from apps.ingestion.services.vector_service import PineconeVectorService
from apps.ingestion.services.processing_service import DocumentProcessingService
from apps.rag_engine.models import QueryAuditLog
from .prompt_service import McpPromptService

logger = logging.getLogger(__name__)


class RagQueryService:
    """
    Enterprise Agentic RAG Service orchestrating multi-tenant semantic retrieval,
    strict metadata filtering, prompt formatting, LLM inference, and audit logging.
    """

    # Similarity cutoff threshold below which context is discarded as irrelevant
    SIMILARITY_THRESHOLD = 0.20

    FALLBACK_RESPONSE = "The provided enterprise documents do not contain sufficient information to answer this inquiry."

    def __init__(self):
        self.vector_service = PineconeVectorService()
        self.processing_service = DocumentProcessingService()
        self.openai_api_key = getattr(settings, 'OPENAI_API_KEY', '')
        self.gemini_api_key = getattr(settings, 'GEMINI_API_KEY', '')
        self.hf_api_key = getattr(settings, 'HUGGINGFACE_API_KEY', '')
        self.model_name = getattr(settings, 'LLM_MODEL_NAME', 'gpt-4o-mini')
        self.temperature = getattr(settings, 'LLM_TEMPERATURE', 0.0)

        # Detect configured live LLM provider
        self.active_provider = None
        if self.openai_api_key and not self.openai_api_key.startswith('mock_'):
            self.active_provider = 'openai'
        elif self.gemini_api_key and not self.gemini_api_key.startswith('mock_'):
            self.active_provider = 'gemini'
        elif self.hf_api_key and not self.hf_api_key.startswith('mock_'):
            self.active_provider = 'huggingface'

        self._openai_client = None

    def _get_openai_client(self):
        if self._openai_client is None:
            from langchain_openai import ChatOpenAI
            self._openai_client = ChatOpenAI(
                model=self.model_name,
                temperature=self.temperature,
                api_key=self.openai_api_key
            )
        return self._openai_client

    def embed_query(self, query_text: str) -> List[float]:
        """
        Embeds the incoming user query using the identical 384-dim Hugging Face model.
        """
        vectors = self.processing_service.generate_embeddings([query_text.strip()])
        return vectors[0]

    def _call_live_llm(self, query: str, context_block: str) -> str:
        """
        Dispatches prompt to configured live LLM provider (OpenAI, Gemini, Hugging Face).
        """
        user_prompt = McpPromptService.build_user_prompt(query, context_block)

        if self.active_provider == 'openai':
            from langchain_core.messages import SystemMessage, HumanMessage
            client = self._get_openai_client()
            messages = [
                SystemMessage(content=McpPromptService.SYSTEM_PROMPT),
                HumanMessage(content=user_prompt)
            ]
            response = client.invoke(messages)
            return response.content.strip()

        elif self.active_provider == 'gemini':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
            payload = {
                "system_instruction": {"parts": [{"text": McpPromptService.SYSTEM_PROMPT}]},
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {"temperature": self.temperature}
            }
            resp = requests.post(url, json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()

        elif self.active_provider == 'huggingface':
            from huggingface_hub import InferenceClient
            client = InferenceClient(token=self.hf_api_key)
            full_prompt = f"<|system|>\n{McpPromptService.SYSTEM_PROMPT}\n<|user|>\n{user_prompt}\n<|assistant|>\n"
            return client.text_generation(
                prompt=full_prompt,
                model="Qwen/Qwen2.5-72B-Instruct",
                max_new_tokens=800,
                temperature=0.1
            ).strip()

        raise RuntimeError(f"Unknown LLM provider: {self.active_provider}")

    def _synthesize_local_response(self, query: str, matches: List[Dict[str, Any]]) -> str:
        """
        High-fidelity, context-aware deterministic synthesis engine for zero-token
        and offline enterprise RAG. Accurately extracts relevant sections, paragraphs,
        and facts from retrieved chunks without sentence clipping or repetitive prefixes.
        """
        if not matches:
            return self.FALLBACK_RESPONSE

        # Deduplicate and sort matches by chunk index to maintain narrative coherence
        sorted_matches = sorted(matches, key=lambda m: (
            m.get('metadata', {}).get('filename', ''),
            m.get('metadata', {}).get('chunk_index', 0)
        ))

        all_lines = []
        doc_filenames = set()
        for m in sorted_matches:
            meta = m.get('metadata', {})
            fname = meta.get('filename', 'Enterprise Document')
            doc_filenames.add(fname)
            raw = meta.get('text', '')
            # Clean up unknown Unicode replacement characters, broken byte marks, and normalize hyphens/bullets
            cleaned = (
                raw.replace('\x8e', '-')
                .replace('\x96', '-')
                .replace('\ufffd', '-')
                .replace('\u2022', '-')
                .replace('\u2013', '-')
                .replace('\u2014', '-')
                .replace('\r\n', '\n')
            )
            # Keep standard printable characters, tabs, and newlines
            cleaned = ''.join(c for c in cleaned if c in ('\n', '\t') or (32 <= ord(c) < 127) or ord(c) in (0x2013, 0x2014, 0x2022))
            for line in cleaned.split('\n'):
                line = line.strip()
                if line:
                    all_lines.append(line)

        # Deduplicate consecutive identical lines
        deduped_lines = []
        for line in all_lines:
            if not deduped_lines or deduped_lines[-1] != line:
                deduped_lines.append(line)

        q_lower = query.lower()

        # Modular Section Extractors
        wants_identity = any(w in q_lower for w in [
            'name', 'candidate', 'who is', 'who was', 'author', 'personal details', 'contact', 'email', 'phone', 'mobile'
        ])
        wants_skills = any(w in q_lower for w in ['skill', 'skills', 'technologies', 'tech stack', 'tools'])
        wants_projects = any(w in q_lower for w in ['project', 'projects', 'built', 'portfolio'])
        wants_exp = any(w in q_lower for w in ['experience', 'work', 'job', 'employment', 'career', 'intern'])
        wants_edu = any(w in q_lower for w in ['education', 'qualification', 'degree', 'college', 'university', 'cgpa', 'bachelor', 'master'])
        is_summary = any(w in q_lower for w in ['summarize', 'summary', 'overview', 'entire', 'whole', 'resume', 'profile', 'about'])

        # Candidate Identity & Personal Details
        if wants_identity:
            return self._extract_candidate_name_and_details(matches)

        # Multi-topic query (e.g. skills + projects + experience)
        if sum([wants_skills, wants_projects, wants_exp, wants_edu]) >= 2:
            multi_sections = []
            if wants_skills:
                skills_text = self._extract_skills_section(deduped_lines)
                if skills_text:
                    multi_sections.append(skills_text)
            if wants_projects:
                proj_text = self._extract_projects_section(deduped_lines)
                if proj_text:
                    multi_sections.append(proj_text)
            if wants_exp:
                exp_text = self._extract_experience_section(deduped_lines)
                if exp_text:
                    multi_sections.append(exp_text)
            if wants_edu:
                edu_text = self._extract_education_section(deduped_lines)
                if edu_text:
                    multi_sections.append(edu_text)

            if multi_sections:
                return "\n\n".join(multi_sections)

        # Single Topic Inquiries
        if wants_edu:
            edu_text = self._extract_education_section(deduped_lines)
            if edu_text:
                return edu_text

        if wants_projects:
            proj_text = self._extract_projects_section(deduped_lines)
            if proj_text:
                return proj_text

        if wants_skills:
            skills_text = self._extract_skills_section(deduped_lines)
            if skills_text:
                return skills_text

        if wants_exp:
            exp_text = self._extract_experience_section(deduped_lines)
            if exp_text:
                return exp_text

        if is_summary:
            return self._extract_comprehensive_summary(deduped_lines)

        # General inquiry fallback: extract high-relevance paragraphs matching query terms
        return self._extract_relevant_passages(query, deduped_lines, doc_filenames)

    def _extract_candidate_name_and_details(self, matches: List[Dict[str, Any]]) -> str:
        """
        High-precision extractor for candidate name, contact info, profiles, and professional summary.
        Works across both single-line headers and multiline resumes.
        """
        import re

        # Find chunk 0 specifically (the root document header)
        chunk0_text = ""
        filename = ""
        for m in matches:
            meta = m.get('metadata', {})
            if meta.get('chunk_index') == 0:
                chunk0_text = meta.get('text', '')
                filename = meta.get('filename', '')
                break

        if not chunk0_text and matches:
            meta = matches[0].get('metadata', {})
            chunk0_text = meta.get('text', '')
            filename = meta.get('filename', '')

        # Combine text across all retrieved chunks for secondary searching
        all_text = " \n ".join([m.get('metadata', {}).get('text', '') for m in matches])
        combined_text = (chunk0_text + "\n" + all_text).strip()

        # 1. Email Extraction
        email = None
        em = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', combined_text)
        if em:
            email = em.group(0).strip()

        # 2. Phone Number Extraction
        phone = None
        ph = re.search(r'(\+?\d[\d\s\-]{8,15}\d)', combined_text)
        if ph:
            phone = ph.group(0).strip()

        # 3. Online Profiles & Portfolios
        profiles = []
        for p in ['LinkedIn', 'GitHub', 'LeetCode', 'Portfolio', 'HackerRank', 'CodeChef']:
            if p.lower() in combined_text.lower() and p not in profiles:
                profiles.append(p)

        # 4. Candidate Name Extraction
        name = None
        lines = [
            l.strip()
            for l in (chunk0_text or '').replace('\r\n', '\n').split('\n')
            if l.strip()
        ]

        SECTION_HEADERS = {
            'EDUCATION', 'EXPERIENCE', 'WORK EXPERIENCE', 'PROFESSIONAL SUMMARY',
            'SUMMARY', 'PROJECTS', 'TECHNICAL SKILLS', 'SKILLS', 'CERTIFICATIONS',
            'ACHIEVEMENTS', 'PROFILE', 'CURRICULUM VITAE', 'RESUME'
        }

        # Pass A: Look for a clean standalone name on the top lines
        for line in lines[:5]:
            u = line.upper().strip()
            if u in SECTION_HEADERS:
                break
            if not any(x in line for x in ['@', '+91', 'http', '.com', 'linkedin', 'github', 'leetcode', 'portfolio']):
                parts = line.split()
                if 2 <= len(parts) <= 4 and len(line) < 40 and not any(char.isdigit() for char in line):
                    name = line.strip()
                    break

        # Pass B: If name shares the line with contact details/links, strip them out cleanly
        if not name:
            for line in lines[:5]:
                u = line.upper().strip()
                if u in SECTION_HEADERS:
                    break
                cleaned = line
                if email:
                    cleaned = cleaned.replace(email, ' ')
                if phone:
                    cleaned = cleaned.replace(phone, ' ')
                cleaned = re.sub(r'(https?://\S+|www\.\S+)', ' ', cleaned)
                for token in ['LinkedIn', 'GitHub', 'LeetCode', 'Portfolio', '|', '•', '·', ':', ',']:
                    cleaned = re.sub(re.escape(token), ' ', cleaned, flags=re.IGNORECASE)
                cand = re.sub(r'\s+', ' ', cleaned).strip()
                if cand:
                    parts = cand.split()
                    if 1 <= len(parts) <= 4 and len(cand) < 40 and not any(char.isdigit() for char in cand):
                        name = cand
                        break

        # Pass C: Fallback to document filename (e.g. ReddyNaresh_Resume V1.docx -> Reddy Naresh)
        if not name and filename:
            base = filename.split('.')[0]
            for suffix in ['_Resume', '_CV', 'Resume', 'CV', ' V1', ' v1', ' V2', ' v2']:
                base = base.replace(suffix, '')
            parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)', base.replace('_', ' ').replace('-', ' '))
            if parts and len(parts) >= 1:
                name = " ".join(parts).title()

        # 5. Extract Professional Summary if available
        summary_text = ""
        for m in matches:
            t = m.get('metadata', {}).get('text', '')
            if 'PROFESSIONAL SUMMARY' in t.upper() or 'SUMMARY' in t.upper():
                s_lines = [l.strip() for l in t.split('\n') if l.strip()]
                capturing = False
                captured = []
                for sl in s_lines:
                    if 'PROFESSIONAL SUMMARY' in sl.upper() or sl.upper() == 'SUMMARY':
                        capturing = True
                        continue
                    if capturing and any(sl.upper().startswith(h) for h in ['TECHNICAL SKILLS', 'SKILLS', 'EDUCATION', 'PROJECTS', 'EXPERIENCE']):
                        break
                    if capturing and len(sl) > 20:
                        captured.append(sl)
                if captured:
                    summary_text = " ".join(captured)
                    break

        # Construct clear, executive-grade response
        output = []
        if name:
            output.append(f"The candidate's name is **{name}**.\n")
            output.append("### Candidate Profile & Contact Details")
            output.append(f"- **Full Name:** **{name}**")
        else:
            output.append("### Candidate Profile & Contact Details")

        if email:
            output.append(f"- **Email Address:** `{email}`")
        if phone:
            output.append(f"- **Phone Number:** `{phone}`")
        if profiles:
            output.append(f"- **Online Profiles:** {' | '.join(profiles)}")

        if summary_text:
            output.append(f"\n### Professional Summary\n{summary_text}")

        return "\n".join(output)

    def _extract_education_section(self, lines: List[str]) -> str:
        edu_entries = []
        for i, line in enumerate(lines):
            l_lower = line.lower()
            if any(deg in l_lower for deg in ['master of', 'bachelor of', 'minor in', 'b.sc', 'mca', 'btech', 'b.tech']):
                entry_lines = [line]
                for nxt in lines[i + 1:i + 4]:
                    if any(h in nxt.upper() for h in ['CERTIFICATION', 'ACHIEVEMENT', 'EXPERIENCE', 'PROJECT', 'SKILL']):
                        break
                    if any(deg in nxt.lower() for deg in ['master of', 'bachelor of', 'minor in', 'b.sc', 'mca', 'btech']):
                        break
                    entry_lines.append(nxt)
                formatted = " - ".join(entry_lines)
                if formatted not in edu_entries:
                    edu_entries.append(formatted)

        if edu_entries:
            lines_out = ["### Educational Qualifications\n"]
            for e in edu_entries:
                lines_out.append(f"- **{e}**")
            return "\n".join(lines_out)
        return ""

    def _extract_projects_section(self, lines: List[str]) -> str:
        proj_entries = []
        current_proj = None
        in_project_section = False

        for line in lines:
            u_line = line.upper()
            if 'PROJECTS' in u_line:
                in_project_section = True
                continue
            if in_project_section and any(u_line.startswith(h) for h in ['EDUCATION', 'CERTIFICATION', 'ACHIEVEMENT', 'WORK EXPERIENCE', 'TECHNICAL SKILLS']):
                in_project_section = False
                if current_proj:
                    proj_entries.append(current_proj)
                    current_proj = None
                continue

            is_contact = any(k in line.lower() for k in ['@', '+91', 'phone', 'linkedin', 'github', 'portfolio', 'leetcode'])
            is_work_exp = any(k in line.lower() for k in ['intern', 'sde', 'engineer', 'developer', 'pvt ltd', 'services', 'present'])
            is_cert = any(k in line.lower() for k in ['certifications:', 'coursera', 'meta', 'google', 'hp life'])
            is_degree = any(k in line.lower() for k in ['master of', 'bachelor of', 'minor in', 'b.sc', 'mca', 'btech', 'cgpa'])

            is_candidate_project = (
                in_project_section
                or any(k in line.lower() for k in ['microservice', 'careerai', 'agentic rag', 'rag pipeline'])
            ) and not (is_contact or is_work_exp or is_cert or is_degree)

            if is_candidate_project and ('|' in line or '–' in line or '—' in line):
                if current_proj:
                    proj_entries.append(current_proj)
                parts = line.split('|') if '|' in line else (line.split('–') if '–' in line else line.split('—'))
                current_proj = {
                    "name": parts[0].strip(),
                    "tech": parts[1].strip() if len(parts) > 1 else "",
                    "bullets": []
                }
            elif current_proj and len(line) > 20 and not (is_contact or is_work_exp or is_cert or is_degree):
                if not any(x in line for x in ['word/', '.xml', '[Content_Types]', 'CERTIFICATIONS']):
                    current_proj["bullets"].append(line)

        if current_proj:
            proj_entries.append(current_proj)

        if proj_entries:
            lines_out = ["### Key Technical Projects\n"]
            for p in proj_entries:
                lines_out.append(f"#### **{p['name']}**")
                if p['tech']:
                    lines_out.append(f"**Technologies:** `{p['tech']}`\n")
                for b in p['bullets']:
                    lines_out.append(f"- {b}")
                lines_out.append("")
            return "\n".join(lines_out).strip()
        return ""

    def _extract_skills_section(self, lines: List[str]) -> str:
        skill_cats = []
        for line in lines:
            if any(cat in line for cat in ['AI & Machine Learning:', 'Software & Backend Engineering:', 'Databases & DevOps:', 'Computer Science Fundamentals:']):
                parts = line.split(':', 1)
                skill_cats.append((parts[0].strip(), parts[1].strip()))

        if skill_cats:
            lines_out = ["### Technical Competencies\n"]
            for title, items in skill_cats:
                lines_out.append(f"- **{title}:** {items}")
            return "\n".join(lines_out)
        return ""

    def _extract_experience_section(self, lines: List[str]) -> str:
        exp_entries = []
        current_exp = None
        for line in lines:
            u_line = line.upper()
            if any(u_line.startswith(h) for h in ['PROJECTS', 'EDUCATION', 'TECHNICAL SKILLS', 'CERTIFICATIONS']):
                if current_exp:
                    exp_entries.append(current_exp)
                    current_exp = None
                continue
            if '|' in line and any(k in line.lower() for k in ['engineer', 'intern', 'sde', 'developer']):
                if current_exp:
                    exp_entries.append(current_exp)
                current_exp = {"header": line.strip(), "bullets": []}
            elif current_exp and len(line) > 20:
                current_exp["bullets"].append(line)

        if current_exp:
            exp_entries.append(current_exp)

        if exp_entries:
            lines_out = ["### Professional Experience\n"]
            for exp in exp_entries:
                lines_out.append(f"#### **{exp['header']}**")
                for b in exp["bullets"]:
                    lines_out.append(f"- {b}")
                lines_out.append("")
            return "\n".join(lines_out).strip()
        return ""

    def _extract_comprehensive_summary(self, lines: List[str]) -> str:
        name_header = lines[0] if lines and len(lines[0]) < 40 else "Candidate Profile"
        lines_out = [f"### Executive Summary: {name_header}\n"]

        # Professional Summary narrative
        summary_lines = []
        capturing = False
        for line in lines:
            if 'PROFESSIONAL SUMMARY' in line.upper():
                capturing = True
                continue
            if capturing and any(line.upper().startswith(h) for h in ['TECHNICAL SKILLS', 'SKILLS', 'WORK EXPERIENCE']):
                break
            if capturing and len(line) > 15:
                summary_lines.append(line)

        if summary_lines:
            lines_out.append(" ".join(summary_lines) + "\n")

        # Skills Overview
        skills_text = self._extract_skills_section(lines)
        if skills_text:
            lines_out.append(skills_text + "\n")

        # Work Experience
        exp_text = self._extract_experience_section(lines)
        if exp_text:
            lines_out.append(exp_text + "\n")

        # Projects
        proj_text = self._extract_projects_section(lines)
        if proj_text:
            lines_out.append(proj_text + "\n")

        # Education
        edu_text = self._extract_education_section(lines)
        if edu_text:
            lines_out.append(edu_text + "\n")

        return "\n".join(lines_out).strip()

        # General inquiry fallback: extract high-relevance paragraphs matching query terms
        return self._extract_relevant_passages(query, deduped_lines, doc_filenames)

    def _extract_relevant_passages(self, query: str, lines: List[str], doc_names: set) -> str:
        """
        General semantic passage extractor for non-resume corporate documents and policies.
        """
        words = set([w.lower() for w in query.split() if len(w) > 3])
        scored_blocks = []

        # Group lines into logical paragraph blocks
        blocks = []
        curr = []
        for line in lines:
            if line.isupper() or len(line) < 30:
                if curr:
                    blocks.append("\n".join(curr))
                    curr = []
            curr.append(line)
        if curr:
            blocks.append("\n".join(curr))

        for b in blocks:
            b_lower = b.lower()
            overlap = sum(1 for w in words if w in b_lower)
            if overlap > 0:
                scored_blocks.append((overlap, b))

        scored_blocks.sort(key=lambda x: x[0], reverse=True)

        if scored_blocks:
            top_passages = [b for _, b in scored_blocks[:3]]
            output = ["### Relevant Document Information\n"]
            for p in top_passages:
                output.append(f"- {p}\n")
            return "\n".join(output).strip()

        # Fallback to the first few comprehensive lines
        output = ["### Document Summary\n"]
        for line in lines[:6]:
            if len(line) > 20:
                output.append(f"- {line}")
        return "\n".join(output).strip() if len(output) > 1 else self.FALLBACK_RESPONSE

    def execute_query(self, tenant_id: str, query: str, top_k: int = 4, document_id: str = None) -> Dict[str, Any]:
        """
        Executes the complete Agentic RAG pipeline strictly partitioned by tenant_id.

        Args:
            tenant_id: UUID string of the authenticated enterprise tenant.
            query: User's natural language question.
            top_k: Number of most similar document chunks to retrieve (default: 4).
            document_id: Optional UUID to constrain search to a specific document.
        """
        start_time = time.perf_counter()
        clean_query = query.strip()

        if not clean_query:
            return {
                "answer": "Query cannot be empty.",
                "citations": [],
                "retrieved_chunk_count": 0,
                "latency_ms": 0.0,
                "tenant_id": str(tenant_id)
            }

        logger.info(f"Executing RAG query for Tenant {tenant_id}: '{clean_query[:60]}...' (doc filter: {document_id})")

        # Dynamically scale retrieval depth for broad questions or single-document queries
        q_lower = clean_query.lower()
        is_broad = any(w in q_lower for w in ['summarize', 'summary', 'overview', 'entire', 'whole', 'all', 'full', 'resume', 'profile', 'document'])
        is_identity = any(w in q_lower for w in [
            'name', 'candidate', 'who is', 'who was', 'author', 'personal details',
            'contact', 'email', 'phone', 'mobile', 'details', 'who created', 'whose'
        ])
        retrieval_k = max(top_k, 10) if (is_broad or document_id or is_identity) else top_k

        # 1. Embed query into 384-dimensional dense vector
        query_vector = self.embed_query(clean_query)

        # Retrieve header chunk #0 for document identity / candidate profile grounding
        header_chunks = []
        if is_identity or is_broad or document_id:
            try:
                header_chunks = self.vector_service.get_header_chunks(
                    tenant_id=str(tenant_id),
                    document_id=document_id
                )
            except Exception as e:
                logger.warning(f"Failed to fetch header chunks: {e}")

        # 2. Vector DB Query with MANDATORY tenant_id metadata filter
        raw_matches = self.vector_service.query_vectors(
            tenant_id=str(tenant_id),
            query_vector=query_vector,
            top_k=retrieval_k,
            document_id=document_id
        )

        # 3. Defense-in-depth: Assert and filter strict tenant isolation
        valid_matches = []
        for match in raw_matches:
            match_tenant = match.get('metadata', {}).get('tenant_id')
            if str(match_tenant) != str(tenant_id):
                logger.critical(
                    f"CRITICAL SECURITY VIOLATION: Vector {match.get('id')} returned for tenant {tenant_id} "
                    f"actually belongs to tenant {match_tenant}. Dropping from context."
                )
                continue

            # Apply similarity relevance threshold (adaptive for document scoping, identity, or broad summarization)
            score = float(match.get('score', 0.0))
            threshold = 0.05 if (document_id or is_broad or is_identity) else self.SIMILARITY_THRESHOLD
            if score >= threshold:
                valid_matches.append(match)

        # If identity or broad query, ensure Chunk 0 is anchored into valid_matches
        if is_identity or is_broad:
            existing_ids = {m.get('id') for m in valid_matches}
            for hc in header_chunks:
                if hc.get('id') not in existing_ids:
                    valid_matches.insert(0, hc)
                    existing_ids.add(hc.get('id'))

        # 4. Handle zero-match or low-relevance scenarios (prevent hallucinations)
        if not valid_matches:
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            from apps.ingestion.models import Document
            uploaded_docs = list(Document.objects.filter(
                tenant_id=tenant_id,
                upload_status='Processed'
            ).values_list('filename', flat=True))

            if uploaded_docs:
                doc_list_str = ", ".join([f"`{d}`" for d in uploaded_docs[:3]])
                is_policy_query = any(w in q_lower for w in ['vacation', 'leave', 'holiday', 'policy', 'handbook', 'hr', 'benefits', 'pto', 'salary', 'payroll'])
                if is_policy_query:
                    fallback_msg = (
                        f"The provided enterprise document(s) in your knowledge vault ({doc_list_str}) "
                        f"do not contain sufficient information regarding company vacation, leave, or HR policies.\n\n"
                        f"**Note:** To query workplace policies, please upload an Employee Handbook or HR Policy document in the **Documents** section."
                    )
                else:
                    fallback_msg = (
                        f"The provided enterprise document(s) ({doc_list_str}) do not contain sufficient information to answer this inquiry.\n\n"
                        f"**Note:** Try rephrasing or upload additional reference documents in the **Documents** section."
                    )
            else:
                fallback_msg = (
                    "The provided enterprise documents do not contain sufficient information to answer this inquiry. "
                    "No processed documents were found in your organization's knowledge vault.\n\n"
                    "**Note:** Please navigate to the **Documents** section and upload documents to begin querying."
                )

            # Record audit log
            self._record_audit_log(
                tenant_id=tenant_id,
                query=clean_query,
                retrieved_matches=[],
                response_text=fallback_msg,
                latency_ms=latency_ms
            )

            return {
                "answer": fallback_msg,
                "citations": [],
                "retrieved_chunk_count": 0,
                "latency_ms": round(latency_ms, 2),
                "tenant_id": str(tenant_id)
            }

        # 5. Extract citation lineage metadata
        citations = []
        for m in valid_matches:
            meta = m.get('metadata', {})
            text_snippet = meta.get('text', '')
            truncated_snippet = (text_snippet[:180] + '...') if len(text_snippet) > 180 else text_snippet
            citations.append({
                "document_id": meta.get('doc_id'),
                "filename": meta.get('filename', 'Unknown'),
                "chunk_index": meta.get('chunk_index', 0),
                "similarity_score": round(float(m.get('score', 0.0)), 4),
                "snippet": truncated_snippet
            })

        # 6. Generate answer (Live LLM or Enhanced Context Synthesizer)
        context_block = McpPromptService.format_context_block(valid_matches)

        if self.active_provider:
            try:
                answer = self._call_live_llm(clean_query, context_block)
            except Exception as e:
                logger.error(f"Live LLM ({self.active_provider}) failed: {e}. Falling back to context synthesizer.", exc_info=True)
                answer = self._synthesize_local_response(clean_query, valid_matches)
        else:
            answer = self._synthesize_local_response(clean_query, valid_matches)

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # 7. Record enterprise audit telemetry
        self._record_audit_log(
            tenant_id=tenant_id,
            query=clean_query,
            retrieved_matches=valid_matches,
            response_text=answer,
            latency_ms=latency_ms
        )

        return {
            "answer": answer,
            "citations": citations,
            "retrieved_chunk_count": len(valid_matches),
            "latency_ms": round(latency_ms, 2),
            "tenant_id": str(tenant_id)
        }

    @staticmethod
    def _record_audit_log(tenant_id: str, query: str, retrieved_matches: List[Dict], response_text: str, latency_ms: float):
        """
        Persists query execution metrics and citations to MySQL/SQLite for auditability & compliance.
        """
        try:
            chunks_summary = [
                {
                    "id": m.get('id'),
                    "score": round(float(m.get('score', 0.0)), 4),
                    "filename": m.get('metadata', {}).get('filename'),
                    "chunk_index": m.get('metadata', {}).get('chunk_index'),
                }
                for m in retrieved_matches
            ]
            QueryAuditLog.objects.create(
                tenant_id=tenant_id,
                query_text=query,
                retrieved_chunks=chunks_summary,
                response_text=response_text,
                latency_ms=round(latency_ms, 2)
            )
        except Exception as e:
            logger.warning(f"Could not record query audit log: {e}")
