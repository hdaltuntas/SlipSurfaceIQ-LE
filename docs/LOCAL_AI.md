# Local AI assistant / Yerel AI asistanı

This feature is available in the development source. The published **2026.1.0
installers do not include it**. No AI subscription, API account or hosted backend
is required. Install Ollama and a local text model separately.

## Türkçe — ilk kurulum

1. [Ollama'yı kurun](https://ollama.com/download). Windows ve Linux desteklenir.
2. **Bulut özelliklerini kapatın** ve Ollama'yı yeniden başlatın:
   - Windows: kullanıcı ortam değişkenlerine `OLLAMA_NO_CLOUD` ekleyin; değerini
     `1` yapın. Sistem tepsisindeki Ollama'yı kapatıp yeniden açın.
   - Linux, systemd hizmeti: `sudo systemctl edit ollama.service` ile aşağıdaki
     satırları ekleyin; ardından `sudo systemctl daemon-reload` ve
     `sudo systemctl restart ollama` çalıştırın:

     ```ini
     [Service]
     Environment="OLLAMA_NO_CLOUD=1"
     ```

   - Terminalden başlatılan Ollama için: `OLLAMA_NO_CLOUD=1 ollama serve`.
   - Alternatif: Ollama'nın çalıştığı kullanıcının `~/.ollama/server.json`
     dosyasında `disable_ollama_cloud` değerini `true` yapın; diğer ayarları koruyun.
3. Bir yerel model indirin. Küçük bir başlangıç örneği:

   ```sh
   ollama pull qwen3:4b
   ```

   Bu model yaklaşık 2,5 GB indirilir; çalışma belleği ihtiyacı dosya boyutundan
   daha fazladır. Hız ve yanıt kalitesi RAM, GPU, model ve bağlam uzunluğuna bağlıdır.
   Örnek model önerisi bir mühendislik yeterlilik doğrulaması değildir.
4. SlipSurfaceIQ'da **Araçlar → Yerel AI Asistanı** menüsünü açın.
5. **Modelleri yenile** düğmesine basın ve indirdiğiniz modeli seçin.
6. Sorunuzu yazın. Projeye özel yardım için **Proje ve güncel sonuçları yerel
   modelle paylaş** seçeneğini açın. **Bağlamı göster** ile veriyi inceleyebilirsiniz.

Örnek sorular: “Yeraltı suyunu nasıl tanımlarım?”, “Girdi kontrolü hangi hatayı
buldu?”, “Mevcut yöntem sonuçlarını karşılaştır.” Asistan proje değiştirmez veya
analiz çalıştırmaz. Yeni bir senaryo için girdileri düzenleyip F5 ile hesaplayın.

Model indirme internet gerektirir. İndirilen yerel modelle sohbet çevrimdışı
çalışabilir. Model ağırlıkları MSI/DEB/RPM/Arch paketlerine dahil edilmez.

## English — setup and behaviour

Install [Ollama](https://ollama.com/download), disable its cloud features with
`OLLAMA_NO_CLOUD=1` in the environment of the Ollama process, then restart it.
For a Linux systemd service use the service override shown above; a shell
environment variable does not configure an already-running service. Alternatively
set `disable_ollama_cloud: true` in the service user's Ollama `server.json` file.
Download a local text model, for example `ollama pull qwen3:4b`.

Open **Tools → Local AI Assistant**, refresh models, select one and ask a question.
Ollama must already be running. Only the port is configurable (default 11434);
the connection host is fixed to `127.0.0.1`. The assistant supports English and
Turkish according to the application language. The source can be launched with
the normal project launchers; no additional Python AI SDK is needed.

## Data and execution boundaries

- Opening the application or panel makes no network request. Refresh and Send
  explicitly contact the loopback Ollama service. HTTP proxies and redirects are
  disabled. There is no remote endpoint, automatic cloud fallback or model pull.
- Cloud entries are filtered from the list. Before each chat, `/api/show` must
  confirm local model metadata and text-completion capability; remote aliases
  are rejected before any question or project data is sent. Disable Ollama's
  cloud features as above as well: the local service configuration is controlled
  by the user, and model metadata could otherwise change between requests.
- Project sharing starts **off**. Enabling it sends solver inputs (including
  geometry, materials and their names, loads, supports, settings), the first
  validation error if any, and current result summaries to the local service.
  Title, author, company, comments, file path, display settings and drawing
  annotations are excluded. Stale results are excluded independently of the UI.
- Questions and successful conversation history are sent even without project
  sharing. No conversation or project context is written to app preferences,
  logs or project files. Only port and selected model are remembered.
- Conversations are cleared on document/result changes, model/port/sharing
  changes and window close. A language/context change starts a new conversation
  on the next request. Closing the dock only hides it; Stop cancels an active request.
- Requests stream plain text with Stop and a five-minute deadline. Metadata
  requests have a ten-second deadline. Incomplete, failed, cancelled and
  output-limited answers are labelled and excluded from subsequent chat history.
- Prompts have a conservative 12,000-byte serialized budget, up to four recent
  successful turns, a 16,384-token requested model context and 1,024 output tokens.
  Older history pairs are dropped to fit. Oversized project contexts are rejected
  explicitly rather than silently truncating solver inputs.
- The model can explain and suggest checks; it has **no execution or mutation
  tools**, no Python console access, no filesystem access and no web search.
  Answers identify guide/project/result sources where the model follows the
  prompt, but those labels are not a factual-verification system. The actual
  solver remains the source of calculated FS; independently review AI commentary.

## Troubleshooting and verification

| Problem | Action |
| --- | --- |
| Cannot connect | Start Ollama; check its port and loopback binding. |
| Empty list | Download a local text model, then refresh. Cloud models are excluded. |
| Model rejected | Check `/api/show` metadata; update Ollama or select a local completion model. |
| Out of memory / slow | Stop; use a smaller model or free RAM/VRAM. |
| Context too large | Disable project sharing for general help; no data is silently cut. |
| Partial reply | Retry with a narrower question; partial text is not used as conversation history. |

Automated tests use a loopback HTTP server to check protocol handling, Unicode
streaming, preflight rejection of cloud aliases, proxy/redirect boundaries,
timeouts, cancellation, input/result grounding and read-only GUI integration.
They do **not** validate the scientific accuracy of any LLM. A real-model quality
evaluation with representative Turkish/English project questions remains required.

References: [Ollama local/cloud configuration](https://docs.ollama.com/faq),
[chat API](https://docs.ollama.com/api/chat),
[model metadata definitions](https://github.com/ollama/ollama/blob/main/api/types.go),
[example model and its license](https://ollama.com/library/qwen3:4b).
