> [!NOTE]
> This is a play project - I built it to learn [sqlite-vec](https://github.com/asg017/sqlite-vec) and to see how far I could get with LLM generated code.
>
> It is 80% LLM generate code, awkwardly stitched together.
>
> It is not intended for production use (or any use at all really), but please feel free to poke at it, fork it, learn from it, and [talk to me about it](https://bsky.app/profile/usher.dev).

# Gitlab Auto PR


https://github.com/user-attachments/assets/a0b4cf08-4d53-443c-88ab-c195a2ae04c8


Watches a Gitlab project for Issues with the `auto-pr` tag and then tries to create a pull request with LLM-generated changes.

Currently only works on a single file.

1. Copy `.env.example` to `.env` and update with your keys
2. Run `uv run src/gitlab_auto_pr.py`

Maybe you could add:

-   Support for multiple files
-   The ability to ask the agent for changes in PR comments
-   A better way to find more relevant files (I'm not sure the embeddings are quite cutting it here)
