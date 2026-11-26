# Changelog

All notable changes to Ráfaga Studio are documented in this file.

## Unreleased

### Added

- Create with AI takes a song or track of yours as background music: it drops while the voice speaks and fades out at
  the end. The Director passes it when you attach a song and ask for a video.
- Paid AI clips that bring their own sound (Gemini, and Kling when its model adds sound) keep it under the
  narration, lower while the voice speaks. Before, the montage muted it.
- Videos end with a short fade to black and silence (ads skip it, because their closing card follows).

### Changed

- The AI Director answers without any key: its instructions did not fit the free AI (it rejected every request). In a
  test of 29 typical requests with the free AI and no keys, it now picks the right first step in most of them.
- With Claude, the Director's instructions stay the same in every step and request, so Claude reads them from its cache
  for an hour: faster and cheaper from the second step.
- The Director never runs the same step with the same arguments twice in one request, and its error messages tell it
  which arguments are valid. Yes/no written as text and Python-style arguments are read correctly.
- Free images for a video and the character sheets of a series are requested three at a time instead of one by one.
  Paid images keep going one by one, so a job that fails midway does not pay for unused images.
- The free text AI waits only what is left of its 30 seconds; OpenAI and Gemini think less on each Director step; the
  OpenAI-compatible client has a time limit.
- A free image service that ran out of today's quota is tried last for the next scenes instead of first.
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
