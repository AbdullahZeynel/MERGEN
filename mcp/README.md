# MCP — hazır demo

`server.py`: Streamable HTTP, yalnızca `127.0.0.1:9010/mcp`. `list_cases`, `get_slice`, `get_overlay`, `get_mesh` araçları VPS'teki `MERGEN_DEMO_ROOT` dizinini salt okunur kullanır. `demo_store.py` dosya sınırlarını ve vaka/indeks/katman eşleşmesini denetler. Tarayıcı doğrudan MCP'ye bağlanmaz. Model/LLM çıkarımı veya kuyruk içermez. [Kurulum ve sözleşme](../docs/DEMO_SERVICES.md).
