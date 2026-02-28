# hackusu_26_data_factory_app

- only has read access
- AD group created
- added Data Classification auto on
- leveraged data lineage through built in features
- column masking personal data (example technicians_name created SQL function to sha2(lower(trim(name)), 256))
- included outside data 3x using faker library python
- created a secret for token in databricks
- set up MCP (Model Context Protocol) server is a lightweight, standardized program that acts as a connector, allowing AI models (LLMs) to securely access external data sources, APIs, and tools
- 

Requested Core Features:

1. Governed Data Access
   -Connect to Unity Catalog tables
   -Demonstrate data lineage
   -Show at least one security feature (row-level security, column masking, or access audit)

2. Visual Dashboard
   - Minimum 3 different visualization types (bar chart, line chart, pie chart)
   - At least 5 KPIs or metrics
   - Interactive elements(filters, drill-downs, date ranges)
  
3. Conversational Interface
   - Text-based chat interface
   - Ability to ask questions in natural language
   - Return data-driven answers
   - Display results as text AND visualizations
  
4. Steering Documents
   - Document your app template structure
   - Define guardrails (data access, security policies)
   - Create user guide for business users
  
5. Governance Framework
  - Define roles and permissions
  - Establish data quality rules
  - Create approval workflow (can be conceptual)

Stretch Goals Hit:
  - Multi-page application with navigation
  - Real-time data updates
  - Export functionality (CSV, PDF)
  - User authentication and personalization
  - AI-generated insights or recommendations
  - Predictive analytics or ML models
  - Workflow orchestration

Other Stretch Goals Hit:
  - Creation of artificial data
  - 

