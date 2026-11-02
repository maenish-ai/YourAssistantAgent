# Arabic female voice – Android integration attempt

This is a **source integration patch**, not a tested APK. The GitHub workflow downloads the model, converts Piper metadata, embeds phonemizer data, compiles an Android TTS runtime, and checks assets in the APK. The phone uses this local runtime preferentially; Android TTS is the fallback if initialization fails. GroqCloud and Windows are unchanged.

**Apply:** Extract the ZIP at the repository root preserving paths, commit the files, then run the `Build Android with bundled female voice` workflow under GitHub Actions. Download the APK artifact if the workflow succeeds. The archive contains modified files only, not the 63.5MB model; CI downloads it.

**Important:** We could not download the model or compile the Android project in this environment. Compatibility of the Piper model, native library, phonemizer, and Kotlin/Java calls needs validation in CI and on a real Android device. Do not treat this as a verified working voice release. A CI failure must be fixed before use. The selected voice is Emirati female, not confirmed to be soft or Jordanian. GPL/espeak and native dependency licensing need review before redistribution.

Sources:
- https://huggingface.co/vadimbelsky/arabic-emirati-female-piper
- https://k2-fsa.github.io/sherpa/onnx/tts/piper.html
- https://github.com/k2-fsa/sherpa-onnx
- https://github.com/XDcobra/react-native-sherpa-onnx/releases
