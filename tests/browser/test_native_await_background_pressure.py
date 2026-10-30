"""A slow collector must not turn continuous diagnostics into a global wait."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import textwrap

import pytest


_PROBE = textwrap.dedent('''
    import json
    import time
    from tests.browser.test_native_await import setup, _click

    fixture = setup.__wrapped__()
    create = next(fixture)
    try:
        support, context, api = create("""
            go.onclick=()=>{
                window.background=setInterval(async()=>{
                    await (await fetch(api+'/api/echo')).json();
                },5);
            };
            other.onclick=async()=>{
                await Promise.resolve();
                await (await fetch(api+'/api/echo')).json();
            };
        """)
        context.page.evaluate("""() => {
            window.cloneCount=0;
            const clone=Response.prototype.clone;
            Response.prototype.clone=function(...args){
                window.cloneCount++;
                return Reflect.apply(clone,this,args);
            };
        }""")
        claims={'associated':0,'background':0}
        original=context.native.session.send
        def delayed_send(method, params=None):
            expression=(params or {}).get('expression','')
            if method=='Runtime.evaluate' and expression.startswith('window.__refractBrowser.claimNative('):
                kind='background' if expression.endswith(',null)') else 'associated'
                claims[kind]+=1
                # A deterministic slow-host control, not a longer action budget.
                time.sleep(.010)
            return original(method, params)
        context.native.session.send=delayed_send
        started=time.monotonic()
        initial=_click(support,context)
        context.page.wait_for_timeout(250)
        current=_click(support,context,'other')
        context.page.evaluate('clearInterval(window.background)')
        result={
            'elapsed':time.monotonic()-started,
            'initial_traffic':len(initial.traffic),
            'traffic':len(current.traffic),
            'claims':claims,
            'clones':context.page.evaluate('cloneCount'),
            'http_requests':len(api.requests),
            'diagnostic_steps':[r.step_id for r in initial.diagnostic_recorded+current.diagnostic_recorded],
        }
    finally:
        try: next(fixture)
        except StopIteration: pass
    print(json.dumps(result))
''')


def test_background_pressure_does_not_starve_awaited_foreground_or_drain_background():
    root = Path(__file__).resolve().parents[2]
    # The external bound also catches a blocked synchronous protocol callback,
    # where an in-browser timer or the ordinary action deadline cannot run.
    process = subprocess.Popen([sys.executable, '-c', _PROBE], cwd=root,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        pytest.fail('background request handling exceeded the external completion bound')
    assert process.returncode == 0, stderr
    result = json.loads(stdout)
    assert result['elapsed'] < 5
    assert result['initial_traffic'] == 0
    assert result['traffic'] == 1
    assert result['claims'] == {'associated': 1, 'background': 0}
    assert result['clones'] == 1
    assert result['http_requests'] > 2
    assert result['diagnostic_steps'] and all(step is None for step in result['diagnostic_steps'])
