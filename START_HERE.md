# Start Here — Computer Architecture Paper Reviewer

Welcome! This project uses Gradio and OpenAI to review research papers against computer architecture conference standards, including ISCA, MICRO, HPCA, and ASPLOS. Reviews are displayed in the application and can be saved as `.txt` files.

## Project Links

- **Hugging Face Space (application):** https://huggingface.co/spaces/AmnaHassan/AI-Paper-Reviewer
- **Hugging Face Dataset (saved reviews/results):** https://huggingface.co/datasets/AmnaHassan/arch-reviews

Both links are currently private. They can be made public if access is needed. If you'd like to use the project under your own account, you can also ask me for help duplicating the Hugging Face Space.

## Use the Project on Hugging Face

1. Create a new Hugging Face Space and select **Gradio** as the SDK.
2. Upload the project files, including `app.py`, `requirements.txt`, and the original `README.md`.
3. In the Space's **Settings → Variables and secrets**, configure the environment variables required by the application:
   - `OPENAI_API_KEY` — required OpenAI API key.
   - `OPENAI_MODEL` — optional model name; the original README specifies `gpt-4o` as the default.
   - `HF_TOKEN` and `HF_REPO_ID` — optional, if the code supports saving reviews to a Hugging Face repository.
   - `HF_REPO_TYPE` — optional repository type, if supported by the code.
4. Start the Space and open the application.

Check the original `README.md` and `app.py` for the exact configuration supported by the current version of the project.

## Run Locally or on Another Platform

Some code may be configured specifically for Hugging Face Spaces. You may need to update platform-specific settings, repository IDs, or storage logic before running it locally or hosting it elsewhere.

A typical local setup is:

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your-openai-api-key"
python app.py
```

On Windows, set the environment variable using the command appropriate for your terminal. Never commit API keys or other secrets to a public repository.

## Where Results Are Stored

The project is configured to use a Hugging Face dataset repository for saved reviews/results. See the original `README.md` and the implementation in `app.py` for the actual storage behavior and required settings. Files stored only in a running Space's local filesystem may not persist across restarts.

If you want to save results to your own repository, configure your own Hugging Face token and repository ID, and make sure the token has the required permissions. Keep unpublished papers and reviews private when appropriate.

## Need Help?

You can upload the provided files to your own Hugging Face Space and add your own API keys and configuration. If you run into issues adapting the code for local use or another hosting platform, feel free to ask me for help or to duplicate my existing Space.
