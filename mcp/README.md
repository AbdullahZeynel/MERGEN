# MCP — hazır demo

`server.py`: Streamable HTTP, yalnızca `127.0.0.1:9010/mcp`. `list_catalog`,
`list_cases`, `get_slice`, `get_overlay`, `get_mesh` araçları VPS'teki
`MERGEN_DEMO_ROOT` dizinini salt okunur kullanır. `list_cases` ve varlık araçları
`module`/`disease` filtresi kabul eder. `demo_store.py` hem eski v2 paketini hem
v3 kataloğunu okur; disk yollarını, vaka/indeks/katman eşleşmesini denetler.
Tarayıcı doğrudan MCP'ye bağlanmaz. Model/LLM çıkarımı veya kuyruk içermez.
[Kurulum ve sözleşme](../docs/DEMO_SERVICES.md).
