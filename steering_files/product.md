# Product Steering: Databricks Data App Factory

## Vision

Empower non-technical business users to deploy governed, self-service data applications
without needing a data engineer or software developer. We combine an AI IDE (Claude Code
or Kiro) with Databricks Apps to translate natural language intent into secure, enterprise-grade
data applications that provide full IT visibility and control.

## Core Challenge

"How do we empower the average business user to deploy governed data applications without
needing to be a data engineer or software developer?"

## User Personas

### Primary: Business Analyst
- Non-technical; wants to ask questions in plain English ("What were sales last quarter?")
- Needs interactive dashboards with clear visualizations
- Cannot write SQL or Python — relies entirely on conversational interface
- Accesses data via governed, pre-approved datasets only

### Secondary: Data Engineer / IT Admin
- Manages Unity Catalog tables, permissions, and governance policies
- Monitors all deployed apps via an IT oversight dashboard
- Can enable/disable apps, set resource limits, and enforce compliance
- Reviews and approves apps before production promotion

### Tertiary: App Developer / Hackathon Participant
- Builds the Data App Factory framework itself
- Uses steering documents to guide the AI IDE
- Iterates on requirements, design, and implementation via Spec-Driven Development

---

## Core Principles

### Self-Service
- The app must be intuitive and conversational — no code required from end users
- Business users describe their desired app in natural language; the system generates it
- Dashboards must be navigable without training

### Governed
- Every data access must go through Unity Catalog with proper permissions
- At least one security feature must be demonstrated: row-level security, column masking, or access audit
- All data interactions must be logged in an audit trail

### Performant
- Dashboards should load quickly with clear, interactive visualizations
- Minimum 3 distinct visualization types (bar, line, pie, scatter, map, etc.)
- Minimum 5 meaningful KPIs or metrics displayed
- Provide filtering and drill-down capabilities

### Conversational
- Embed a chatbot that allows users to "chat with data"
- Support natural language queries (e.g., "Show me top products by revenue this quarter")
- Return data-driven answers with both text explanations AND visualizations

### Secure by Default
- No hardcoded credentials — use `.env` for local dev; `databricks.sdk.core.Config()` auto-resolves credentials in Databricks Apps
- Parameterized queries only — never raw string interpolation in SQL
- Role-based access control (viewer, analyst, admin) enforced at the app layer

---

## Success Criteria (Hackathon Scoring)

The finished Data App Factory solution MUST:

1. **Pull from Governed Data Sources**
   - Connect to Unity Catalog tables with proper permissions
   - Demonstrate row-level security OR column masking
   - Show audit trail capabilities (log every query with user, timestamp, query text)

2. **Visualize Key Metrics & KPIs**
   - Display interactive dashboards
   - Include at least 3–5 meaningful visualizations
   - Provide filtering and drill-down capabilities

3. **Include Conversational Interface**
   - Embed a chatbot for natural language queries
   - Support questions like "What were sales last quarter?"
   - Return data-driven answers with visualizations

4. **Include Steering Documents**
   - Document the app template structure
   - Define guardrails (data access policies, security policies)
   - Create a user guide for business users

5. **Implement Governance Framework**
   - Define user roles and permissions
   - Establish data quality validation rules
   - Create an approval workflow concept (even if conceptual)

---

## Value Proposition

Make building governed data apps as easy for business users as creating a slideshow,
while maintaining enterprise-grade security, auditability, and architectural standards.
