"""Drive the PIME backend's server.py exactly like PIMELauncher would (stdin/stdout JSON lines).

    python tests_pime_sim.py [python.exe] [backend dir]   (defaults: this python, pime_backend)
"""
import json, os, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")

python = sys.argv[1] if len(sys.argv) > 1 else sys.executable
backend = sys.argv[2] if len(sys.argv) > 2 else "pime_backend"
GUID = "{91c07699-318c-401b-b934-56ef6706da0b}"
VK = {"\n": 0x0D, "\b": 0x08, "\x1b": 0x1B, "DOWN": 0x28}
env = dict(os.environ, PYTHONIOENCODING="utf-8")
p = subprocess.Popen([os.path.abspath(python), "server.py"], cwd=backend, stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
seq = 0
def call(method, **kw):
    global seq; seq += 1
    msg = {"method": method, "seqNum": seq, **kw}
    p.stdin.write("c1|" + json.dumps(msg) + "\n"); p.stdin.flush()
    while True:
        line = p.stdout.readline()
        if not line:
            sys.exit("backend died:\n" + p.stderr.read())
        if line.startswith("PIME_MSG|"):
            return json.loads(line.split("|", 2)[2])
def key(ch, shift=False):
    states = [0] * 256
    if shift: states[0x10] = 0x80
    code = VK.get(ch, ord(ch.upper()) if len(ch) == 1 else 0)
    char = ord(ch) if len(ch) == 1 and ch not in ("DOWN",) else 0
    ev = dict(charCode=char, keyCode=code, repeatCount=1, scanCode=0, isExtended=False, keyStates=states)
    if not call("filterKeyDown", **ev).get("return"):
        return {"passthrough": ch}
    return call("onKeyDown", **ev)

print(call("init", id=GUID, isWindows8Above=True, isMetroApp=False, isUiLess=False, isConsole=False))
print(call("onActivate", isKeyboardOpen=True))
def typ(s):
    r = None
    for ch in s:
        r = key(ch)
    return r
r = typ("su3cl3"); print("after su3cl3:", r.get("compositionString"), r.get("candidateList"))
r = key("\n"); print("enter ->", r.get("commitString"), "| comp:", repr(r.get("compositionString")))
assert r.get("commitString") == "你好", r
r = typ("ji3au/6wu0 u.3meeting"); print("mixed:", r.get("compositionString"), r.get("candidateList"))
assert r.get("compositionString") == "我明天有meeting", r
r = key("DOWN"); print("down ->", r.get("candidateCursor"), r.get("compositionString"))
assert r.get("candidateCursor") == 1, r
r = key("\n"); print("enter ->", r.get("commitString"))
r = key("<", shift=True); print("shift+, ->", r.get("commitString"))
assert r.get("commitString") == "，", r
r = typ("2/3ji3i vu84"); print("typo 等我一下:", r.get("compositionString"))
assert r.get("compositionString") == "等我一下", r
r = key("\x1b"); print("esc -> comp", repr(r.get("compositionString")), "show", r.get("showCandidates"))
assert not r.get("compositionString"), r
r = key(" "); print("space when idle:", r)
assert r == {"passthrough": " "}, r
p.stdin.close(); p.wait()
print("ALL OK")
