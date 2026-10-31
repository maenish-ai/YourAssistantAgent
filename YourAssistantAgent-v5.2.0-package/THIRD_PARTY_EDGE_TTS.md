# Experimental optional Arabic voice: edge-tts

- Repository: https://github.com/rany2/edge-tts
- Upstream license: LGPLv3 for most source files; the upstream `srt_composer.py` uses MIT. See the complete upstream LICENSE at https://github.com/rany2/edge-tts/blob/master/LICENSE
- `edge-tts` is an unofficial client of Microsoft's online neural speech endpoint. It is **not** an officially supported, guaranteed-free or private speech API, and must not be represented as running on Groq.
- The Windows builder adds its license text in `licenses/edge-tts-LICENSE.txt` when creating the distributable.
- Usage can send text to Microsoft; opt-in required before selecting Sana for ordinary assistant responses. The default voice remains official Groq Noura.
- The project does not vendor a Microsoft speech model or include any Microsoft credentials.
- Ensure redistribution of the bundled LGPL library complies with all applicable license requirements, including the proper notices and conditions for relinking/replacement where applicable.
