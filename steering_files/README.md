# Steering Files: HackUSU 2026 — Databricks Data App Factory

These steering files are designed for use with **Claude Code**, **Kiro**, or any AI IDE
that supports spec-driven development via steering/context documents.

Copy this entire `steering_files/` directory to `.kiro/steering/` (for Kiro) or reference
it directly in your Claude Code context before generating any code.

---

## What Are Steering Files?

Steering files encode your organization's standards, constraints, and patterns so an AI
coding assistant builds *your* app — not a generic one. They answer the questions:

- "What are we building and why?" → `product.md`
- "What tools and constraints apply?" → `tech.md`
- "How should the code be organized?" → `structure.md`
- "What governance rules must be enforced?" → `governance.md`
- "What security policies apply to every line of code?" → `security.md`
- "How should LLMs and AI be integrated?" → `llm.md`

The AI reads all of these before generating any code, requirements, or design documents.

---

## File Reference

| File | Purpose | Key Topics |
|---|---|---|
| [`product.md`](product.md) | Vision, personas, success criteria | Core challenge, user roles, judging criteria |
| [`tech.md`](tech.md) | Stack, constraints, dependencies | Databricks Free Edition limits, frameworks, SDK usage |
| [`structure.md`](structure.md) | Directory layout, file contracts | Exact folder tree, naming conventions, page registry pattern |
| [`governance.md`](governance.md) | Data governance & IT oversight | RBAC, audit trail, guardrails, kill switch, approval workflow |
| [`security.md`](security.md) | Security policies | No hardcoded secrets, SQL injection prevention, error handling |
| [`llm.md`](llm.md) | AI/LLM integration | Genie API, Strands/Bedrock, Text-to-SQL, prompt patterns |

---

## How to Use with Claude Code

Paste this prompt to start a new project after loading these steering files:

```
I have populated the steering files (product.md, tech.md, structure.md, governance.md,
security.md, llm.md). Read all of them carefully.

Based on those standards, I want to build a '[YOUR USE CASE]' Gradio app for the
HackUSU 2026 Databricks Data App Factory hackathon.

Generate:
1. requirements.md — functional and non-functional requirements
2. design.md — architecture diagram (ASCII), component breakdown, data flow
3. tasks.md — ordered implementation checklist I can execute step by step
```

Replace `[YOUR USE CASE]` with one of the ideas from Appendix C of the hackathon PDF:
- "Supply Chain Monitor" — inventory visibility, supplier scorecards, delay alerts
- "Sales Dashboard Factory" — regional sales, rep performance, trend analysis
- "HR Analytics Studio" — headcount, turnover, diversity metrics
- "Customer Insights Hub" — segmentation, campaign performance, customer journey
- "Financial KPI Tracker" — P&L views, budget vs. actual, variance analysis

---

## How to Use with Kiro

1. Copy all `.md` files to `.kiro/steering/` in your project workspace
2. Open the Kiro **Spec** panel
3. Click **New Spec**
4. Enter the prompt above (with your chosen use case)
5. Kiro will read the steering files and generate `requirements.md`, `design.md`, `tasks.md`

---

## Hackathon Success Checklist

Before submitting, verify your app satisfies all judging criteria:

### Governed Data Access
- [ ] App connects to Unity Catalog tables (`catalog.schema.table` format)
- [ ] At least one security feature implemented: row-level security OR column masking
- [ ] Audit trail is logging every query (timestamp, user, query, row count)

### Visual Dashboard
- [ ] At least 3 different chart types (bar, line, pie, scatter, etc.)
- [ ] At least 5 KPI metrics displayed
- [ ] Filters and interactive drill-downs work

### Conversational Interface
- [ ] Chat input accepts natural language questions
- [ ] Responses include both text AND data/visualization
- [ ] Multi-turn conversation works (follow-up questions retain context)

### Steering Documents
- [ ] This steering set is committed to your repo
- [ ] `governance/roles.yaml` defines viewer/analyst/admin permissions
- [ ] `governance/guardrails.yaml` defines allowed SQL operations and resource limits
- [ ] `README.md` in your app includes a user guide for business users

### Governance Framework
- [ ] RBAC enforced at the page level (nav_guard pattern)
- [ ] SQL guardrail validator runs on all LLM-generated queries
- [ ] Admin page shows IT oversight dashboard (or is at least described conceptually)

### Judging Criteria (HackUSU scoring)
- **Technology:** Impressive? Difficult problem? Clever technique used?
- **Design:** Well-designed UI/UX? Impressive graphics? Does it actually work?
- **Learning:** Did you try something new? Especially important for beginner prize.

---

## Key URLs & Resources

### Databricks Documentation
| Resource | URL |
|---|---|
| Databricks Apps (get started) | https://docs.databricks.com/aws/en/dev-tools/databricks-apps/get-started |
| Databricks Apps overview | https://docs.databricks.com/aws/en/dev-tools/databricks-apps/ |
| AI/BI Genie overview | https://docs.databricks.com/aws/en/genie/ |
| Genie Conversation API | https://docs.databricks.com/aws/en/genie/conversation-api |
| Unity Catalog overview | https://docs.databricks.com/en/data-governance/unity-catalog/ |
| Free Edition setup | https://docs.databricks.com/aws/en/getting-started/free-edition |
| Free Edition limitations | https://docs.databricks.com/aws/en/getting-started/free-edition-limitations |
| Community Edition migration | https://docs.databricks.com/aws/en/getting-started/ce-migration |
| Databricks community forums | https://community.databricks.com/ |

### Video Tutorials
| Title | URL |
|---|---|
| Getting Started with Databricks Apps (official) | https://docs.databricks.com/aws/en/dev-tools/databricks-apps/get-started |
| Databricks Apps intro video | https://www.databricks.com/resources/demos/videos/databricks-apps-introduction |
| Deploy AI Chatbots in Minutes | https://www.youtube.com/watch?v=Wg9w4MBpXw0 |
| Build Quick Apps — Streamlit, Gradio, Dash, Flask | https://www.youtube.com/watch?v=mgdu_YhIVr8 |
| Create a RAG-based Chatbot with Databricks | https://www.youtube.com/watch?v=p4qpIgj5Zjg |
| Learn Databricks for Free (End-to-End) | https://www.youtube.com/watch?v=gV2zCoE1Xss |

### Training & Certifications (Free)
| Course | Duration | URL |
|---|---|---|
| Databricks Fundamentals Accreditation | ~2 hours | https://www.databricks.com/learn/training/home |
| Generative AI Fundamentals Accreditation | ~1 hour | https://www.databricks.com/learn/training/home |
| AI Agent Fundamentals Accreditation | ~1.5 hours | https://www.databricks.com/learn/training/home |

### Recommended Blog Posts
| Title | URL |
|---|---|
| Introducing Databricks Apps | https://www.databricks.com/blog/introducing-databricks-apps |
| Building a Chatbot with LLMs | https://www.databricks.com/solutions/accelerators/building-a-chatbot-with-large-language-models |
| RAG Chatbot with Databricks and Pinecone | https://www.databricks.com/blog/implementing-rag-chatbot-using-databricks-and-pinecone |
| Mastering Databricks Apps | https://www.tredence.com/blog/mastering-databricks-apps-from-creation-to-deployment-of-interactive-data-applications |

### AI IDE Tools
| Tool | URL | Use For |
|---|---|---|
| Kiro (AWS AI IDE) | https://kiro.dev/ | Spec-driven development with these steering files |
| Cursor AI | https://cursor.sh/ | Alternative AI code editor |
| Claude Code (Anthropic) | — | CLI AI assistant (you are using this now) |
| Strands Agents SDK | https://strandsagents.com/latest/ | Building multi-step AI agents on Bedrock |

### Databricks Marketplace (Free Sample Datasets)
| Dataset | Publisher | Domain |
|---|---|---|
| Supply Chain Inventory & Transaction Analytics | Dataplatr | Manufacturing |
| Predictive Maintenance & Asset Management | Dataknobs | Manufacturing |
| Global Tariffs and Duties Datafeed | Trademo | Trade |
| Enterprise Software Sales Dataset | Databricks | Sales |
| Oracle Financial AP Invoice | Dataplatr | Finance |

### Reference Code
| Resource | URL | Notes |
|---|---|---|
| **Official Databricks App Templates** | https://github.com/databricks/app-templates | Start here |
| `gradio-data-app` | https://github.com/databricks/app-templates/tree/main/gradio-data-app | **Primary reference** — SQL Warehouse + `Config()` auth + `gr.Blocks` + `gr.ScatterPlot` |
| `gradio-hello-world-app` | https://github.com/databricks/app-templates/tree/main/gradio-hello-world-app | Minimal starter — verify your `app.yaml` and `demo.launch()` pattern works first |
| `agent-langgraph` | https://github.com/databricks/app-templates/tree/main/agent-langgraph | Full conversational agent with LangGraph + MLflow if you need more than Genie |
| `e2e-chatbot-app-next` | https://github.com/databricks/app-templates/tree/main/e2e-chatbot-app-next | Chat UI querying foundation models — good reference for the chat tab pattern |
| Gradio Docs — Blocks | https://www.gradio.app/docs/gradio/blocks | Full `gr.Blocks` API reference |
| Gradio Docs — Chatbot | https://www.gradio.app/docs/gradio/chatbot | `gr.Chatbot` + `type="messages"` format |
| Gradio Docs — ChatInterface | https://www.gradio.app/docs/gradio/chatinterface | Simplest chatbot wrapper |
| Gradio Docs — Request | https://www.gradio.app/docs/gradio/request | `gr.Request` for reading headers (user identity) |
| Databricks End-to-End Data Science | https://github.com/Berkeley-Data/e2e-data-science | Full workflow reference |

---

## Glossary (from hackathon PDF)

| Term | Definition |
|---|---|
| AI/BI Genie | Databricks feature for natural language data queries |
| Databricks Apps | Platform for building and deploying full-stack data applications within Databricks |
| Data App Factory | Conceptual framework for enabling business users to create data applications |
| Delta Lake | Open-source storage layer providing ACID transactions |
| Governed Data | Data with defined access controls, quality rules, and compliance policies |
| Gradio | Python library for building ML web applications |
| Guardrails | Security and policy constraints that govern app creation and deployment |
| Lakehouse | Data architecture combining data lake and data warehouse capabilities |
| RAG | Retrieval Augmented Generation — AI technique for grounding LLM responses in specific data |
| Steering Document | Template and guidelines that define app creation patterns |
| Streamlit | Python library for creating data web applications |
| Unity Catalog | Unified governance solution for data and AI assets in Databricks |

---

## Common Pitfalls (from hackathon PDF)

1. **Overcomplicating the solution** — Start simple, add complexity incrementally. Focus on core requirements first.
2. **Ignoring governance** — Governance is not optional; it is core to the challenge. Don't treat security as an afterthought.
3. **Poor user experience** — Business users are non-technical. Make it intuitive. Test with someone unfamiliar with your app.
4. **Weak conversational interface** — Chat should actually work, not just be a static form. Test with real questions business users would ask.
5. **Insufficient steering documents** — Don't just describe your app — describe the *template system*. Show how business users would use YOUR framework to create THEIR apps.
6. **Data connection issues** — Test data connections early. Have fallback sample data.
7. **Last-minute integration** — Integrate components continuously. Don't wait until the last hour.

---

## Hackathon Contact

- Brandon Piliero, Account Executive — Brandon.Piliero@databricks.com
- Elise Hollowed, Manager, University Alliances — Elise.Hollowed@databricks.com
- Alex Jorna, Solution Architect — Alex.Jorna@databricks.com
- Anant Asthana, Solution Architect — Anant.Asthana@databricks.com
