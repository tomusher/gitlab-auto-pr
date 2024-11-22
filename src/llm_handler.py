import os
import hashlib
from anthropic import Anthropic
from pathlib import Path
import sqlite3
import sqlite_vec
import sqlite_lembed


class CodebaseLLM:
    def __init__(self, db_path="embeddings.db"):
        self.anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.db_path = db_path
        self.db = self._setup_db()

        self.excluded = {".git", "__pycache__", "venv", "node_modules", "build", "dist"}
        self.code_extensions = {
            ".py",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".java",
            ".cpp",
            ".hpp",
            ".c",
            ".h",
            ".cs",
            ".go",
            ".rb",
            ".php",
            ".swift",
            ".kt",
            ".tf",
            ".toml",
        }

    def _setup_db(self):
        """Setup SQLite database with vector extension"""
        db = sqlite3.connect(self.db_path)
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        sqlite_lembed.load(db)
        db.enable_load_extension(False)

        db.executescript(
            """
                INSERT INTO temp.lembed_models(name, model)
                select 'jinav2', lembed_model_from_file('models/jina-embeddings-v2-small-en-q5_k_m.gguf');
            """
        )

        # Create tables for file index and file hashes
        db.executescript(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS file_embeddings 
            USING vec0(
                id INTEGER PRIMARY KEY,
                embedding float[512],
                path TEXT NOT NULL,
                hash TEXT NOT NULL,
                +content TEXT NOT NULL,
            );
        """
        )
        return db

    def _get_file_hash(self, path, content):
        """Generate a hash of the file content"""
        return hashlib.sha256(content.encode()).hexdigest()

    def _needs_update(self, path, content):
        """Check if file needs to be reindexed"""
        current_hash = self._get_file_hash(path, content)
        cursor = self.db.execute(
            "SELECT hash FROM file_embeddings WHERE path = ?", (path,)
        )
        result = cursor.fetchone()
        return result is None or result[0] != current_hash

    def _index_files(self, repo_path):
        """Index all files in the repository"""
        updated_files = 0
        processed_paths = set()

        for path in Path(repo_path).rglob("*"):
            if (
                path.is_file()
                and not any(x in path.parts for x in self.excluded)
                and path.suffix in self.code_extensions
            ):
                print("Indexing file:", path)
                try:
                    content = path.read_text()
                    relative_path = str(path.relative_to(repo_path))
                    processed_paths.add(relative_path)

                    # Check if file needs updating
                    if not self._needs_update(relative_path, content):
                        continue

                    # Delete old entry if exists
                    self.db.execute(
                        "DELETE FROM file_embeddings WHERE path = ?", (relative_path,)
                    )

                    hash = self._get_file_hash(relative_path, content)

                    cursor = self.db.execute(
                        """INSERT INTO file_embeddings (path, content, hash, embedding) 
                           VALUES (?, ?, ?, lembed('jinav2', ?))""",
                        (relative_path, content, hash, content[:500]),
                    )

                    updated_files += 1

                except (UnicodeDecodeError, OSError):
                    continue

        # Remove entries for deleted files
        cursor = self.db.execute("SELECT path FROM file_embeddings")
        existing_paths = {row[0] for row in cursor.fetchall()}
        deleted_paths = existing_paths - processed_paths

        if deleted_paths:
            placeholders = ",".join("?" * len(deleted_paths))
            self.db.execute(
                f"DELETE FROM file_embeddings WHERE path IN ({placeholders})",
                tuple(deleted_paths),
            )

        self.db.commit()
        return updated_files

    def _call_anthropic(self, messages, system=None):
        """Make a call to the Anthropic API"""
        kwargs = {
            "model": "claude-3-5-sonnet-latest",
            "max_tokens": 4096,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        return self.anthropic_client.messages.create(**kwargs)

    def _get_relevant_files(self, repo_path, issue_description, max_files=20):
        """Get relevant files using vector similarity search"""
        # Update index for any changed files
        updated_count = self._index_files(repo_path)
        if updated_count > 0:
            print(f"Updated embeddings for {updated_count} modified files")

        # Get all file names from the database for context
        cursor = self.db.execute("SELECT path, content FROM file_embeddings")
        all_files = {row[0]: row[1] for row in cursor.fetchall()}

        # Find similar files
        query = """
            SELECT 
                f.path,
                f.content,
                distance
            FROM file_embeddings f
            WHERE f.embedding match lembed('jinav2', ?)
            AND k = ?
        """

        results = self.db.execute(query, (issue_description, max_files)).fetchall()

        # Ask LLM to identify most relevant file
        file_context = "\n".join([f"- {path}" for path, _, _ in results])
        file_selection_prompt = f"""Given this issue description:
{issue_description}

And these available files:
{file_context}

Which single file is most likely to need changes? Respond with just the file path, nothing else."""
        response = self._call_anthropic(
            [
                {"role": "user", "content": file_selection_prompt},
            ]
        )

        # Print relevance scores for debugging
        for path, _, distance in results:
            print(f"File: {path}, Relevance: {distance:.3f}")

        most_relevant = response.content[0].text.strip()
        print(f"LLM selected {most_relevant} as the most relevant file")
        return {most_relevant: all_files[most_relevant]}

    def _build_prompt(self, context, issue_description):
        """Build prompt for the LLM"""
        return f"""
Based on the following codebase and issue description, provide the entire file with the changes applied.

{context}

Issue Description:
{issue_description}

Do not return any other text, only provide the entire file with the changes applied. Do not include code blocks (```) in your response.
"""

    def process_codebase(self, repo_path, issue_description):
        """Process the codebase and return proposed changes"""
        files = self._get_relevant_files(repo_path, issue_description)

        if not files:
            raise ValueError("No relevant files found for the given issue description")

        context = self._build_context(files)
        prompt = self._build_prompt(context, issue_description)

        response = self._call_anthropic(
            messages=[{"role": "user", "content": prompt}],
            system="You are a helpful programming assistant. Provide the entire file with the changes applied in response to the issue description.",
        )

        first_key = list(files.keys())[0]
        return {first_key: response.content[0].text}

    def _build_context(self, files):
        """Build context string from files"""
        context = "Current codebase:\n\n"
        for path, content in files.items():
            context += f"File: {path}\n```\n{content}\n```\n\n"

        return context

    def format_changes(self, changes):
        """Format changes for MR description"""
        description = "Changes made:\n\n"
        for file, diff in changes.items():
            description += f"Modified `{file}`:\n```diff\n{diff}\n```\n\n"
        return description
