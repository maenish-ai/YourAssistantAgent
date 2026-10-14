from pathlib import Path


def test_github_deploy_module_importable():
    from your_assistant_agent.github_deploy import GitHubDeployer, GitHubDeployError
    assert GitHubDeployer is not None
    assert GitHubDeployError is not None


def test_ui_declares_github_deploy_import():
    ui_source = (Path(__file__).resolve().parents[1] / 'your_assistant_agent' / 'ui.py').read_text(encoding='utf-8')
    assert 'from .github_deploy import GitHubDeployer, GitHubDeployError' in ui_source
    assert (Path(__file__).resolve().parents[1] / 'your_assistant_agent' / 'github_deploy.py').exists()
