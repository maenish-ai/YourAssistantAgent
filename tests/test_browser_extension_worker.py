"""Exercise the shipped worker with mocked Chrome APIs, without a real account."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

NODE = shutil.which("node")
WORKER = Path(__file__).resolve().parents[1] / "browser_extension" / "background.js"
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is needed for browser worker tests")

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const flush = async () => { for (let i=0; i<30; i++) await Promise.resolve(); };
function makeWorker(overrides={}) {
  const handlers = {};
  const events = name => ({addListener: callback => {handlers[name] = callback;}});
  const requests = [];
  const closed = [];
  const alarms = [];
  const context = {
    URL, Map, Set, Promise, Error, Number, String, Date,
    navigator: {userAgent: 'test-browser'},
    setInterval: () => 1,
    setTimeout: callback => { callback(); return 1; },
    location: {href: 'https://www.facebook.com/'},
    document: {querySelector: () => null},
    chrome: {
      tabs: {
        query: async () => [{id:1}],
        create: async ({url}) => ({id:5, url}),
        get: async () => ({id:5, status:'complete'}),
        remove: async id => {closed.push(id);},
      },
      scripting: {executeScript: async ({func, args=[]}) => [{result: await func(...args)}]},
      alarms: {create: async (...args) => {alarms.push(args);}, onAlarm: events('alarm')},
      runtime: {onStartup: events('startup'), onInstalled: events('installed')},
      action: {onClicked: events('click')},
    },
    fetch: async (url, options) => {
      requests.push({url, options});
      return {ok:true, json:async () => ({command:null})};
    },
  };
  Object.assign(context, overrides);
  vm.createContext(context);
  vm.runInContext(source, context);
  return {context, handlers, requests, closed, alarms};
}
"""


def run_worker(script):
    result = subprocess.run(
        [NODE, "-e", HARNESS + "\n(async () => {\n" + script +
         "\n})().catch(error => { console.error(error); process.exitCode=1; });", str(WORKER)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_alarm_resumes_polling_after_worker_timers_are_gone():
    manifest = json.loads((WORKER.parent / "manifest.json").read_text())
    assert "alarms" in manifest["permissions"]
    run_worker(r"""
const worker = makeWorker();
await flush();
assert.equal(worker.alarms[0][0], 'yaa-browser-bridge');
assert.ok(worker.handlers.startup && worker.handlers.installed && worker.handlers.click);
worker.requests.length = 0;
worker.handlers.alarm({name:'unrelated'});
await flush();
assert.equal(worker.requests.length, 0);
worker.handlers.alarm({name:'yaa-browser-bridge'});
await flush();
assert.ok(worker.requests.some(r => r.url.endsWith('/hello')));
assert.ok(worker.requests.some(r => r.url.endsWith('/next-command')));
""")


def test_poll_serializes_commands_and_retries_results_without_reexecuting():
    run_worker(r"""
const worker = makeWorker();
await flush();
let commands = 0, opens = 0, acks = 0;
let release;
worker.context.chrome.tabs.create = async () => {
  opens++;
  await new Promise(resolve => {release = resolve;});
  return {id:9, url:'https://example.com'};
};
worker.context.fetch = async (url) => {
  if (url.endsWith('/next-command')) {
    commands++;
    return {ok:true, json:async () => ({command:commands === 1 ? {
      id:'once', action:'open_url', arguments:{url:'https://example.com'}
    } : null})};
  }
  if (url.endsWith('/command-result')) return {ok:++acks > 1};
  return {ok:true};
};
const first = worker.context.poll();
await flush();
await worker.context.poll();
assert.equal(commands, 1);
assert.equal(opens, 1);
release();
await first;
await worker.context.poll();
assert.equal(acks, 2);
assert.equal(opens, 1);
""")


def test_expired_command_is_reported_without_opening_a_page():
    run_worker(r"""
const worker = makeWorker();
await flush();
let result;
worker.context.chrome.tabs.create = async () => {throw new Error('must not execute');};
worker.context.fetch = async (url, options) => {
  if (url.endsWith('/next-command')) return {ok:true, json:async () => ({command:{
    id:'expired', action:'open_url', arguments:{url:'https://example.com'}, expires_at:1
  }})};
  if (url.endsWith('/command-result')) result = JSON.parse(options.body).result;
  return {ok:true};
};
await worker.context.poll();
assert.equal(result.error, 'command_expired');
""")


def test_session_check_requires_positive_evidence_and_closes_temporary_tabs():
    run_worker(r"""
const worker = makeWorker();
await flush();
for (const [url, hasLogin, expected] of [
  ['https://www.facebook.com/', false, 'unknown'],
  ['https://www.facebook.com/login.php', false, 'not_connected'],
  ['https://www.facebook.com/me', true, 'not_connected'],
  ['https://www.facebook.com/checkpoint/123', false, 'checkpoint'],
  ['https://www.facebook.com/profile.php?id=123', false, 'unknown'],
  ['https://www.facebook.com/test.profile', false, 'unknown'],
  ['https://other.example/profile', false, 'unknown'],
]) {
  worker.context.location.href = url;
  worker.context.document.querySelector = selector => hasLogin && selector.includes("input[") ? {} : null;
  const result = await worker.context.execute({action:'facebook_session'});
  assert.equal(result.status, expected, url);
  assert.equal(result.ok, expected !== 'unknown');
}
assert.equal(worker.closed.length, 7);
worker.context.location.href = 'https://www.facebook.com/test.profile';
worker.context.document.querySelector = selector => selector.includes('[role=') ? {} : null;
assert.equal((await worker.context.facebookSession()).status, 'connected');
""")


def test_page_load_timeout_does_not_run_script_and_always_closes_tab():
    run_worker(r"""
const worker = makeWorker();
await flush();
let clock = 0;
worker.context.Date = {now: () => {clock += 5000; return clock;}};
worker.context.chrome.tabs.get = async () => ({status:'loading'});
let scripts = 0;
worker.context.chrome.scripting.executeScript = async () => {scripts++; return [];};
await assert.rejects(worker.context.facebookSession(), /finish loading/);
assert.equal(scripts, 0);
assert.deepEqual(worker.closed, [5]);
""")
