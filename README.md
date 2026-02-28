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
