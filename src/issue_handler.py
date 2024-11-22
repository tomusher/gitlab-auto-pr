class IssueHandler:
    def __init__(self, project):
        self.project = project

    def get_auto_pr_issues(self):
        """Get all open issues with 'auto-pr' label that haven't been processed"""
        issues = self.project.issues.list(state="opened", labels=["auto-pr"])
        return [i for i in issues if not self._is_processed(i)]

    def _is_processed(self, issue):
        """Check if issue has already been processed"""
        return any(
            label in issue.labels for label in ["auto-pr-complete", "auto-pr-failed"]
        )

    def update_issue_with_mr(self, issue, mr):
        """Add merge request reference to issue"""
        issue.notes.create({"body": f"Created merge request: {mr.web_url}"})

    def mark_issue_processed(self, issue):
        """Mark issue as processed"""
        labels = issue.labels
        labels.append("auto-pr-complete")
        issue.labels = labels
        issue.save()

    def mark_issue_failed(self, issue, error):
        """Mark issue as failed with error message"""
        labels = issue.labels
        labels.append("auto-pr-failed")
        issue.labels = labels
        issue.save()
        issue.notes.create({"body": f"Failed to create auto-PR:\n```\n{error}\n```"})
