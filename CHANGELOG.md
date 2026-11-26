# Changelog

All notable changes to Ráfaga Studio are documented in this file.

## 1.2.0 (2026-11-26)

### Added

- Create with AI takes a song or track of yours as background music: it drops while the voice speaks and fades out at
  the end. The Director passes it when you attach a song and ask for a video with it in the background.
- Paid AI clips keep the sound they bring. Photo to video keeps the ambient sound of a Gemini clip, and in videos,
  ads and series, Kling clips with sound (its 3.0 Turbo model) keep it under the narration, lower while the voice
  speaks. Before, both were muted.
- Videos from Create with AI and series episodes end with a short fade to black and silence (ads with a closing card
  skip it, because the card follows).

### Changed

- The AI Director answers without any key: its instructions did not fit the free AI, which rejected every request. In
  a test of 29 typical requests with the free AI and no keys, it picked the right first step in 23 to 25 of them
  (before: none).
- With Claude, the Director's instructions stay the same in every step and request, so Claude reads them from its cache
  for an hour after its last use: faster and cheaper from the second step (the first step of each hour costs a little
  more, to store them).
- The Director does not run the same step with the same arguments twice in one request (except the next chapter of a
  series and the lists). When it gets the arguments wrong, the error tells it which ones are valid. Yes/no written as
  text and Python-style arguments are read correctly.
- Free images in Create with AI, ads and series episodes, and the character sheets of a series, are requested three at
  a time instead of one by one. Paid images keep going one by one, so a job that fails midway does not pay for unused
  images. Music videos, Design and a Pollinations account with its key still go one by one.
- The free text AI waits only what the service asks for (it now allows one reply every 45 seconds and says when to
  retry), instead of a fixed wait after each refusal. Without keys, Director steps that come right after another reply
  take close to a minute each. OpenAI and Gemini think less on each Director step, and the OpenAI-compatible client
  has a time limit.
- A free image service (Cloudflare or Hugging Face) that ran out of today's quota is tried last for the next hour
  instead of first.
- Ads: the web research has a 150-second limit, trimmed scenes keep the call to action and narration is never cut
  mid-word. If AI video fails in one ad variant, the next variants do not wait for it again.
- Shorts, ads and music videos check the format before downloading or spending anything.
- A series is found by part of its title, and characters are recognized even with different accents or capital letters.

## 1.1.0 (2026-11-03)

### Added

- Choose your voice on every job: when you have ElevenLabs, the studio asks before narrating a video, an ad or a series
  whether to use the free voice or ElevenLabs, with the cost. In AI keys, "Narration voice" keeps one voice fixed.
- Auto-place in the video: write the voice-over in the editor's Audio panel and each sentence lands on its scene, as a
  separate clip you can move or undo. Before any part of your video leaves your PC, it asks for permission on every job.
  The voice-over text goes to the voice service, as in any narration.
- The AI Director now sees your studio settings: which services are connected, what each job would use and which ones are
  not responding, so it can answer questions such as "which voice am I using?". That summary never includes your keys,
  your file paths or your YouTube account.

### Changed

- Paid images and songs now show their maximum cost and ask first from every page, as they already did in the Director.
- Paid narration is not paid twice: redoing a chapter or a shot, or repeating Auto-place, only pays for what is missing.
  If ElevenLabs fails midway, the job continues with the free voice and tells you.
- Text written for a paid voice stays within the budget quoted before you accept.
- The privacy notice now covers these features, so the app shows it again.

### Fixed

- A path written by the AI as a tool name can no longer grant access to that file in the next request.
- With the studio locked, shorts and subtitles through the Director run for free on your PC instead of being refused.
- When a free text AI rejects a request as too large, the studio tries your next free text AI instead of failing.

## 1.0.0 (2026-11-02)

First public release.

### Added

- AI Director: plans and runs complete jobs from a text or voice request, in a full-page chat with visible attachments
  and results.
- Create with AI: prompt to finished video with AI motion, voice-over, subtitles and a studio finish.
- Photo to video, with a choice of camera moves.
- Design, Video editor, Magic Shorts, Ads, Music, Recording booth, Cartoons, Viral niches and Publish.
- AI avatar in the video editor (beta).
- One key box that recognizes each service, encrypted key storage and a connection checker.
- Support for 15 AI services, including Modal, Gemini, Kling and Seedance.
- MCP server with 17 tools for Claude and other agents.
- Ráfaga Guardia: logs what the app blocks, checks the integrity of its code and can lock sensitive features.
- Windows installer, and an interface in English, Spanish, Portuguese and French.

### Changed

- The project is now free software under the GNU GPL-3.0.
