import os
import gitlab
import tempfile
import git
import subprocess
from pathlib import Path
from llm_handler import CodebaseLLM
from issue_handler import IssueHandler
from dotenv import load_dotenv

load_dotenv()


class GitlabAutoPR:
    def __init__(self):
        self.gitlab_url = os.getenv("GITLAB_URL")
        self.gitlab_token = os.getenv("GITLAB_TOKEN")
        self.project_id = os.getenv("GITLAB_PROJECT_ID")
        self.gl = gitlab.Gitlab(self.gitlab_url, private_token=self.gitlab_token)
        self.project = self.gl.projects.get(self.project_id)

        # Ensure model is downloaded before initializing LLM
        self._ensure_model_downloaded()

        self.llm = CodebaseLLM()
        self.issue_handler = IssueHandler(self.project)

    def _ensure_model_downloaded(self):
        """Ensure the embedding model is downloaded before proceeding."""
        script_path = Path(__file__).parent / "download_model.sh"
        if not script_path.exists():
            raise FileNotFoundError("download_model.sh script not found")

        try:
            subprocess.run(["bash", str(script_path)], check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to download model: {e}")

    def clone_repo(self, temp_dir):
        repo_url = self.project.http_url_to_repo.replace(
            "https://", f"https://oauth2:{self.gitlab_token}@"
        )
        return git.Repo.clone_from(repo_url, temp_dir)

    def create_branch(self, repo, issue_id):
        new_branch = f"auto-pr/issue-{issue_id}"
        new = repo.create_head(new_branch)
        new.checkout()
        return new_branch

    def create_merge_request(self, branch_name, issue_id):
        title = f"Auto PR for Issue #{issue_id}"
        description = f"Automated changes for issue #{issue_id}"

        mr = self.project.mergerequests.create(
            {
                "source_branch": branch_name,
                "target_branch": "main",
                "title": title,
                "description": description,
            }
        )
        return mr

    def apply_changes(self, temp_dir, changes):
        """
        Apply the changes to files in the temporary directory.

        Args:
            temp_dir (str): Path to temporary directory containing the repository
            changes (dict): Dictionary mapping file paths to their new content

        Returns:
            dict: Results of applying changes, mapping file paths to status information
        """
        results = {}

        for file_path, new_content in changes.items():
            try:
                # Construct full path
                full_path = Path(temp_dir) / file_path

                # Create parent directories if they don't exist
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # Write the new content to the file
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                results[file_path] = {
                    "status": "success",
                    "message": "Changes applied successfully",
                }
            except Exception as e:
                results[file_path] = {"status": "error", "message": str(e)}

        return results

    def process_issue(self, issue):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clone the repository
            repo = self.clone_repo(temp_dir)

            # Create a new branch
            branch_name = self.create_branch(repo, issue.iid)

            # Get the changes from LLM
            changes = self.llm.process_codebase(temp_dir, issue.description)

            # Apply the changes and get results
            results = self.apply_changes(temp_dir, changes)

            # Check if any changes failed to apply
            failed_changes = {
                path: result
                for path, result in results.items()
                if result["status"] == "error"
            }

            if failed_changes:
                error_msg = "Failed to apply changes to:\n"
                for path, result in failed_changes.items():
                    error_msg += f"- {path}: {result['message']}\n"
                raise Exception(error_msg)

            # Commit and push changes
            repo.index.add("*")
            repo.index.commit(f"Auto changes for issue #{issue.iid}")
            repo.remote().push(branch_name)

            # Create merge request
            mr = self.create_merge_request(branch_name, issue.iid)

            # Update issue with MR link
            self.issue_handler.update_issue_with_mr(issue, mr)

    def run(self):
        while True:
            issues = self.issue_handler.get_auto_pr_issues()
            for issue in issues:
            try:
                self.process_issue(issue)
                self.issue_handler.mark_issue_processed(issue)
            except Exception as e:
                print(f"Error processing issue {issue.iid}: {str(e)}")
                self.issue_handler.mark_issue_failed(issue, str(e))


if __name__ == "__main__":
    auto_pr = GitlabAutoPR()
    auto_pr.run()
