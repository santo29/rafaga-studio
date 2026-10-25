# Changelog · Historial de versiones

## 1.0.0 · 2026-10-24

First public version · Primera versión.

- **AI Director** with push-to-talk voice control (local Whisper) and a glowing border while it listens and works.
- **Create with AI:** prompt → script → images → voice → animation → karaoke subtitles. New: **talking characters
  with lip sync** (Gemini Omni, paid): never used unless asked; Create shows the cost first, the Director asks before
  using it, and there is a per-video cap.
- **Magic Shorts**, **Ads** with your real product, **Music** and music videos, **Recording booth**, **Viral niches**.
- **Design studio** with editable layers and an AI designer; **video editor** with beat-synced effects, filters,
  subtitle styles and templates; **animated series** with original characters and voices.
- **MCP server** with 17 tools shared with the Director.
- Free-first cloud rotation for images and video, and bring-your-own-keys for 15 AI providers.
- Interface in Spanish, English, Portuguese and French.
- Privacy notice, terms and third-party notices; Hugging Face and Gradio telemetry turned off.
- **Design that understands you:** the AI first works out what you meant (typos included, it asks when unsure),
  draws real illustrations (vector, sticker, tattoo, poster, engraving) instead of stock photos, never invents prices
  or contacts, and has new types for illustrations and t-shirt prints. **Illustrator-style workspace** with tool
  column, zoom and hand, align, properties and layers, and «Generate with AI» as a new layer. Six gothic and
  decorative OFL fonts.
- **Cartoons studio:** storyboard with every shot, redo a single shot, draw a missing character sheet, and no more
  episodes made of plain colour when the free image quota runs out.
- **Coherent AI:** the Director picks the right tool, passes your words through and lets each specialist write; every
  AI that reads your request understands typos the same way; clear quota errors without account IDs.
- **Gemini Nano Banana images** as an opt-in provider (paid), auto-detecting the newest model of your key.
- **Design Pro:** Photoshop-style blend modes and image adjustments (brightness, contrast, saturation, blur),
  remove background, **Edit with AI** on an image layer, a quality selector and 4K / 3000×3000 export.
- **Smart studio:** the Director works by departments, each with its own quality rules; it shows the plan and the
  cost and asks before paying or publishing (also by voice), and remembers your preferences per department only
  after you say yes (it never stores keys, PINs or cards). Paid image providers are used only if you pick them.
- **Publish:** schedule videos on YouTube with your own Google app (OAuth with PKCE, resumable upload).
- **Music:** Gemini Lyria first (about US$0.08 per song), ElevenLabs as the second option, with clear errors.
- **Windows installer** (Inno Setup): official portable Python and hash-verified libraries, per-user, no admin rights.
- **Kling and Seedance** (paid video, opt-in only): animate scenes and make talking scenes with their own audio.
  Connected with their own «Connect» button (a key is never guessed to be theirs), never used in Automatic, no
  fallback that could charge twice, the maximum cost is shown before every job, a cap of 15 paid clips per job, and
  scenes already animated are never paid again. The paid service is fixed when a job starts: choosing another one
  mid-job never pays anything that was not asked. Kling 4.0 is left out until its launch price is official. Over
  MCP, anything that costs money, publishes, saves to the studio memory or uses a file from outside the agent's
  folder needs a "Yes" in a native Ráfaga Studio window that the agent cannot read or answer.
- **Security review (Ráfaga Guardia):** the YouTube question names the video and shows the whole description; the
  memory question shows exactly what is saved; in voice mode the real cost is read first; redoing a cartoon episode
  counts every shot it may draw; Hugging Face Spaces cannot redirect requests to your local network; subtitles no
  longer go through FFmpeg's demuxers; links through Windows junctions to network shares are refused; free AI
  answers have a total time and size limit; "fake-ip" proxies are opt-in; the Modal token never sits in the app's
  environment; `PYTHONPATH` from other programs no longer reaches the app's child processes or the MCP server; key
  fragments are never sent to the AI; settings are written atomically; a temporary DPAPI failure no longer sets your
  keys aside; no plaintext backup of Claude's config; the installer always installs inside your profile, removes
  the MCP registration on uninstall and only takes prebuilt wheels; the lock quarantine checks the newest file of a
  version; the Demucs model is verified with its full SHA-256.
- **Ráfaga Guardia, the guardian inside the app:** a new «🛡️ Ráfaga Guardia» page at the end of the menu, with a
  shield that turns green, amber or red. It logs locally what the app stops (network paths, local-network links and
  redirects, fake-ip proxies, fake files, Director and MCP refusals, keys from another service, DPAPI failures, a keys
  file changed by another program, sensitive data refused by the memory) without keys, signed URLs or full paths;
  checks the app's code against an integrity manifest built by the installer; checks the keys file, the install
  folder, the MCP registration and the Demucs model; and **locks** paid video, images, music and voice, publishing,
  the memory and MCP when the code changed or an MCP agent insists after 3 «No» in 10 minutes. Only a person on the
  page can unlock it. Serious
  events show a Windows notification; «Explicar con IA» explains an event in plain words (the AI never acts). The
  launcher `.bat` also opens the installed copy. Privacy notice version 7.
- **Ráfaga Guardia review:** while locked, ElevenLabs voices and uploads from the Publish page do not start and OpenAI
  transcription falls back to the free local Whisper (the lock texts now say exactly what stops); the integrity check
  also sees planted `.pyc`/`.pyw`/`.pyd` files and packages, and the MCP server runs it when it starts; a hijacked MCP
  registration (`-c` code, a script in between, a proxy in `env`, another connection type or a project-scope entry)
  is «peligro»; the installer deletes the old code before copying, so an update never locks the app; unlocking with
  the app open twice no longer locks it again; one incident, one notification of each kind; a single «No» to an agent
  or a key pasted in the wrong box no longer turns the shield amber; an unreadable `guardia.json` counts as locked; a
  lock file kept fresh by another program no longer freezes the window; long file names stay readable in events.
