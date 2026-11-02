FIX FOR GitHub Actions run 41505278135

1. Open GitHub Desktop > Repository > Show in Explorer.
2. Extract this ZIP directly into the repository root, merging .github and replacing build-windows.yml.
3. Double-click REMOVE-DUPLICATE.bat to delete the duplicate workflow.
4. In GitHub Desktop confirm the modified build-windows.yml AND deleted android-female-voice.yml appear under Changes.
5. Commit and Push origin.

This fixes the confirmed Windows duplicate workflow check and missing Python onnx module in the canonical Android job. New build errors may still occur.
