from pathlib import Path

from your_assistant_agent.browser_discovery import (
    _extract_executable_from_command,
    classify_browser_executable,
)


def test_extract_browser_command_paths():
    assert _extract_executable_from_command('"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --single-argument %1').lower().endswith('chrome.exe')
    assert _extract_executable_from_command('C:\\Apps\\Browser\\browser.exe "%1"').lower().endswith('browser.exe')


def test_classifies_primary_and_unsupported_browsers():
    assert classify_browser_executable(Path('chrome.exe'), 'Google Chrome') == ('chromium', 'full')
    assert classify_browser_executable(Path('msedge.exe'), 'Microsoft Edge') == ('chromium', 'full')
    assert classify_browser_executable(Path('brave.exe'), 'Brave') == ('chromium', 'experimental')
    assert classify_browser_executable(Path('firefox.exe'), 'Mozilla Firefox') == ('firefox', 'unsupported')
