# First-run walkthrough

Complete the installation steps in the [README](../README.md) and keep Ollama,
FastAPI, and Vite running. No paid API key is needed.

## Check readiness

Open http://127.0.0.1:8000/api/health. The `status` should be `ready`.
If it is `missing_models`, pull the model names listed in `missing_models`.
If it is `offline`, start Ollama and retry.

## Ask a question with a known answer

1. Open http://127.0.0.1:5173.
2. Upload [examples/project-brief.txt](../examples/project-brief.txt).
3. Verify the document shows a chunk count and its checkbox is selected.
4. Ask: **What is the launch date and who leads the project?**
5. The answer should identify **15 September 2027** and **Mira**, with a citation.
6. Click the citation to inspect the supporting excerpt. TXT uses chunk numbers.
7. Ask: **What is the main risk and its mitigation?**
8. Check that the answer describes delayed furniture and temporary seating.

## Verify evidence boundaries

Ask **What is Mira's home address?** The brief contains no address; the assistant
should say the evidence is insufficient. If it invents one, treat the response
as a model error. Citations help inspection but do not guarantee correctness.

Upload a second file and select only one document at a time. The selected IDs
filter retrieval on each question. Older chat messages remain visible, but they
are conversational context rather than source evidence.

## Verify persistence and deletion

Reload the page and reopen the conversation in the sidebar. Its messages and
source excerpts should remain. Restart FastAPI from the same `backend` directory
to check storage persistence.

Delete the sample document through the library. It should disappear from the
library and future searches. Previously saved chat source excerpts remain until
you delete that conversation as well.

## Expected validation

The backend suite tests extraction, upload failures, retrieval scope, chat
atomicity, and real Chroma persistence/filtering/deletion without Ollama.
The walkthrough above additionally checks a live local model. Model quality and
latency vary with your hardware and model selection.
