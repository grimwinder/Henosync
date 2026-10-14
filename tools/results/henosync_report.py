#!/usr/bin/env python3
"""
henosync_report.py - turn Henosync mission-run logs into a human-readable report.

Usage
    python henosync_report.py                      # reads ~/.henosync/runs, writes ./henosync_report.html
    python henosync_report.py PATH_TO_RUNS_DIR     # any folder of run folders (or a single run folder)
    python henosync_report.py -o out.html --open   # choose output file, open it in your browser afterwards

Pure Python 3.8+ standard library. The HTML it writes is a single self-contained file
(no internet, no CDN), so you can email it or keep it next to the logs.

What it reads (per run folder): meta.json, summary.json, steps.jsonl, operations.jsonl,
events.jsonl, status.jsonl, telemetry.jsonl, robot.jsonl.  Missing/partial files are tolerated.
"""
import argparse
import json
import math
import re
import sys
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

MOVE_V = 0.05          # m/s above which a robot counts as "moving"
GRID_DT = 0.25         # seconds, resampling grid for position data
FILE_ORDER = ["summary.json", "meta.json", "steps.jsonl", "operations.jsonl",
              "events.jsonl", "status.jsonl", "telemetry.jsonl", "robot.jsonl"]
FILE_DESC = {
    "summary.json": "The final scorecard: overall outcome plus one result row per step (duration, target, where the robot ended up, error).",
    "meta.json": "A snapshot of the mission as it was launched: the step list and parameters, every robot's configuration, and the map markers/zones.",
    "steps.jsonl": "Start and end stamps for each step, exactly as the mission runner executed them.",
    "operations.jsonl": "Live status updates from whichever plugin is running (e.g. Auto Navigate, Teleop): running / completed plus a status line.",
    "events.jsonl": "Operator-facing alerts and notices (info / warning / critical), e.g. 'Node Lost'.",
    "status.jsonl": "Changes in each robot's connection status (online, degraded, ...).",
    "telemetry.jsonl": "The raw sensor stream from every robot: position, heading, battery, speed. By far the biggest file.",
    "robot.jsonl": "The robot's own log from its onboard controller: its pose, the velocity it commanded, waypoints reached, and when it lost and regained Henosync. Records made while disconnected arrive after the link returns ('recv' is when Henosync got them).",
}
CMD_V, CMD_W = 0.01, 0.05   # m/s, rad/s - onboard command counts as "driving"


# ----------------------------------------------------------------------------- helpers
def read_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def read_jsonl(p):
    out, bad = [], 0
    if not p.exists():
        return out, 0
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                v = json.loads(line)
                if isinstance(v, dict):
                    out.append(v)
                else:
                    bad += 1
            except Exception:
                bad += 1
    return out, bad


def iso_epoch(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def rel(t):
    """seconds -> '+m:ss'"""
    if t is None:
        return "?"
    t = max(0, t)
    return "+%d:%02d" % (int(t // 60), int(t % 60))


def dur(s):
    if s is None:
        return "?"
    s = float(s)
    if s < 60:
        return "%.0f s" % s
    return "%dm %02ds" % (int(s // 60), int(round(s % 60)) % 60 if round(s % 60) < 60 else 0)


def plural(n, word, plural_word=None):
    return "%d %s" % (n, word if n == 1 else (plural_word or word + "s"))


def percentile(vals, p):
    if not vals:
        return None
    v = sorted(vals)
    return v[min(len(v) - 1, int(round(p / 100.0 * (len(v) - 1))))]


def r3(x):
    return None if x is None else round(x, 3)


def resample(pts, dt=GRID_DT):
    """pts: sorted [(t,x,y,...)] -> hold-last samples on a regular grid."""
    out, i, t = [], 0, pts[0][0]
    end = pts[-1][0]
    while t <= end + 1e-9:
        while i + 1 < len(pts) and pts[i + 1][0] <= t:
            i += 1
        out.append((t, pts[i][1], pts[i][2]))
        t += dt
    return out


def speeds(g, dt=GRID_DT):
    """central-difference speed over a 1 s window"""
    n, k = len(g), int(round(0.5 / dt))
    if n <= 2 * k:
        return [0.0] * n
    sp = [0.0] * n
    for i in range(k, n - k):
        a, b = g[i - k], g[i + k]
        sp[i] = math.dist((a[1], a[2]), (b[1], b[2])) / (b[0] - a[0])
    for i in range(k):
        sp[i] = sp[k]
    for i in range(n - k, n):
        sp[i] = sp[n - k - 1]
    return sp


# ----------------------------------------------------------------------------- one run
def analyse_run(d):
    meta = read_json(d / "meta.json") or {}
    summ = read_json(d / "summary.json") or {}
    steps_log, _ = read_jsonl(d / "steps.jsonl")
    ops, _ = read_jsonl(d / "operations.jsonl")
    events, _ = read_jsonl(d / "events.jsonl")
    status, _ = read_jsonl(d / "status.jsonl")
    tele, bad_tele = read_jsonl(d / "telemetry.jsonl")
    robot_log, _ = read_jsonl(d / "robot.jsonl")

    recvs = [r["recv"] for lst in (steps_log, ops, events, status, tele) for r in lst
             if isinstance(r.get("recv"), (int, float))]
    t0 = meta.get("started") or summ.get("started") or (min(recvs) if recvs else 0)
    t_last = max(recvs) if recvs else t0
    finished = bool(summ.get("ended"))
    t_end = (summ.get("ended") or t_last) - t0
    outcome = summ.get("outcome") or "incomplete"

    # ---- robots
    nodes = {}
    for n in meta.get("nodes") or []:
        nodes[n["id"]] = {"id": n["id"], "name": n.get("name") or n["id"][:6], "plugin": n.get("plugin_id") or "",
                          "cfg": n.get("config") or {}, "meta_batt": n.get("battery_percent")}
    for r in status:
        nodes.setdefault(r.get("node_id"), {"id": r.get("node_id"), "name": r.get("name") or str(r.get("node_id"))[:6],
                                            "plugin": "", "cfg": {}, "meta_batt": None})
    for r in tele:
        nid = r.get("node_id")
        if nid and nid not in nodes:
            nodes[nid] = {"id": nid, "name": nid[:6], "plugin": "", "cfg": {}, "meta_batt": None}
    name_of = lambda nid: nodes.get(nid, {}).get("name", "?") if nid else None

    # ---- markers
    markers = {m["id"]: m for m in meta.get("markers") or []}

    # ---- steps
    meta_steps = meta.get("steps") or []
    results = {r.get("step"): r for r in summ.get("results") or []}
    sev = defaultdict(dict)
    for e in steps_log:
        sev[e.get("index")][e.get("event")] = e
    n_steps = max(len(meta_steps), len(results), (max(sev) + 1) if sev else 0)
    assigned = set()
    steps = []
    for i in range(n_steps):
        ms = meta_steps[i] if i < len(meta_steps) else {}
        res = results.get(i + 1, {})
        params = ms.get("params") or {}
        step_nodes = []
        for v in params.values():
            for x in (v if isinstance(v, list) else [v]):
                if isinstance(x, str) and x in nodes:
                    step_nodes.append(x)
        assigned.update(step_nodes)
        s_ev = sev.get(i, {})
        start = s_ev["start"]["recv"] - t0 if "start" in s_ev else None
        end = s_ev["end"]["recv"] - t0 if "end" in s_ev else None
        tx, ty = res.get("target_x_m"), res.get("target_y_m")
        mk = markers.get(params.get("marker_id"))
        if tx is None and mk and mk.get("map_mode") == "vicon":
            tx, ty = mk["lon"], mk["lat"]
        steps.append({
            "n": i + 1, "name": res.get("step_name") or ms.get("name") or "Step %d" % (i + 1),
            "type": res.get("step_type") or ms.get("plugin_id") or "", "plugin": ms.get("plugin_id") or "",
            "display": ms.get("display_name") or "",
            "robot": res.get("robot") or (name_of(step_nodes[0]) if step_nodes else ""),
            "robot_id": step_nodes[0] if step_nodes else None,
            "target": res.get("target") or (mk or {}).get("name") or "",
            "tx": tx, "ty": ty, "fx": res.get("final_x_m"), "fy": res.get("final_y_m"), "err": res.get("final_error_m"),
            "start": start, "end": end,
            "duration": res.get("duration_s") if res.get("duration_s") is not None else (end - start if None not in (start, end) else None),
            "outcome": res.get("outcome") or (s_ev.get("end", {}).get("outcome")) or ("running" if start is not None else "not started"),
            "status_text": res.get("status_text") or (s_ev.get("end", {}).get("status_text")) or "",
            "coverage": res.get("coverage_pct"),
            "op_done": None, "settle": None, "idle_after": None, "travel_s": None, "path_m": None, "straight_m": None,
        })

    # ---- operations grouped per run of a plugin
    groups = defaultdict(list)
    for o in ops:
        groups[o.get("started_at")].append(o)
    op_list = []
    for k, lst in groups.items():
        lst.sort(key=lambda o: o.get("recv", 0))
        st = (iso_epoch(k) - t0) if iso_epoch(k) else lst[0]["recv"] - t0
        done = next((o["recv"] - t0 for o in lst if (o.get("status") or {}).get("state") in
                     ("completed", "failed", "cancelled", "error", "stopped")), None)
        op_list.append({"start": st, "done": done, "plugin": lst[0].get("plugin_id"),
                        "state": (lst[-1].get("status") or {}).get("state"), "used": False})
    for s in steps:
        if s["start"] is None:
            continue
        best = min((o for o in op_list if not o["used"]), key=lambda o: abs(o["start"] - s["start"]), default=None)
        if best and abs(best["start"] - s["start"]) < 3:
            best["used"] = True
            s["op_done"] = best["done"]

    # ---- teleop command stream
    cmd = []
    rx = re.compile(r"linear=([+-]?[\d.]+)\s+angular=([+-]?[\d.]+)")
    for o in sorted(ops, key=lambda o: o.get("recv", 0)):
        m = rx.search((o.get("status") or {}).get("status_text") or "")
        if m:
            cmd.append((o["recv"] - t0, float(m.group(1)), float(m.group(2))))

    # ---- telemetry per robot
    T = defaultdict(lambda: {"pos": [], "batt": [], "all": [], "spd": []})
    for r in tele:
        nid, tr, v = r.get("node_id"), r.get("recv"), r.get("values") or {}
        if nid is None or tr is None:
            continue
        n = T[nid]
        n["all"].append(tr - t0)
        if v.get("vicon_x") is not None and v.get("vicon_y") is not None:
            n["pos"].append((tr - t0, v["vicon_x"], v["vicon_y"], v.get("vicon_heading")))
        if v.get("battery_percent") is not None:
            n["batt"].append((tr - t0, v["battery_percent"]))
        if isinstance(v.get("speed"), (int, float)):
            n["spd"].append(abs(v["speed"]))
    for n in T.values():
        n["pos"].sort()
        n["batt"].sort()
        n["all"].sort()

    series = {"path": {}, "speed": {}, "dist": {}, "batt": {}, "rate": {}, "cmd": [[r3(a), b, c] for a, b, c in cmd]}
    grids = {}
    robots = []
    n_sec = int(math.ceil(t_end)) + 1
    moving_idx = set()
    for nid, nd in nodes.items():
        t = T.get(nid)
        pos_ok = bool(t and len(t["pos"]) > 1)
        rb = {"id": nid, "name": nd["name"], "plugin": nd["plugin"], "assigned": nid in assigned,
              "pos": pos_ok, "n_samples": len(t["all"]) if t else 0, "first_t": None, "last_t": None,
              "rate_hz": None, "silent_s": 0, "max_gap": 0, "batt": None, "speed_p95": None,
              "pos_source": nd["cfg"].get("position_source"), "vicon_name": nd["cfg"].get("vicon_object_name")}
        if t and t["all"]:
            a = t["all"]
            rb["first_t"], rb["last_t"] = a[0], a[-1]
            rb["rate_hz"] = len(a) / max(a[-1] - a[0], 1e-6) if len(a) > 1 else None
            rb["max_gap"] = max([y - x for x, y in zip(a, a[1:])] or [0])
            rb["silent_s"] = max(0.0, t_end - a[-1]) if (finished or True) else 0
            cnt = [0] * n_sec
            for x in a:
                if 0 <= int(x) < n_sec:
                    cnt[int(x)] += 1
            series["rate"][nid] = cnt
            if t["spd"]:
                rb["speed_p95"] = percentile(t["spd"], 95)
        if t and t["batt"]:
            b = [x[1] for x in t["batt"]]
            rb["batt"] = {"start": sorted(b[:5])[len(b[:5]) // 2], "end": sorted(b[-5:])[len(b[-5:]) // 2],
                          "min": min(b), "max": max(b), "jitter": max(b) - min(b)}
            series["batt"][nid] = [[r3(x), r3(y)] for x, y in t["batt"][::4]]
        if pos_ok:
            g = resample(t["pos"])
            sp = speeds(g)
            grids[nid] = (g, sp)
            series["path"][nid] = [[r3(a), r3(b), r3(c)] for a, b, c in g[::2]]
            series["speed"][nid] = [[r3(g[i][0]), r3(sp[i])] for i in range(0, len(g), 2)]
            if nid in assigned:
                for i, (gt, _, _) in enumerate(g):
                    if sp[i] > MOVE_V:
                        moving_idx.add(int(round(gt / GRID_DT)))
        robots.append(rb)
    rb_by = {r["id"]: r for r in robots}

    # ---- step-level motion analysis
    for s in steps:
        nid = s["robot_id"]
        if nid not in grids or s["start"] is None:
            continue
        g, sp = grids[nid]
        a, b = s["start"], s["end"] if s["end"] is not None else t_end
        idx = [i for i, (gt, _, _) in enumerate(g) if a <= gt <= b]
        mv = [i for i in idx if sp[i] > MOVE_V]
        if mv:
            s["travel_s"] = g[mv[0]][0] - a
            s["settle"] = g[mv[-1]][0]
            if s["end"] is not None and s["end"] - s["settle"] > 0:
                s["idle_after"] = s["end"] - s["settle"]
            path = 0.0
            for i in idx[:-1]:
                if sp[i] > MOVE_V:
                    path += math.dist((g[i][1], g[i][2]), (g[i + 1][1], g[i + 1][2]))
            s["path_m"] = path
            s["straight_m"] = math.dist((g[idx[0]][1], g[idx[0]][2]), (g[mv[-1]][1], g[mv[-1]][2]))
        if s["tx"] is not None:
            seg = [[r3(g[i][0]), r3(math.dist((g[i][1], g[i][2]), (s["tx"], s["ty"])))] for i in idx[::2]]
            series["dist"].setdefault(nid, [])
            if series["dist"][nid]:
                series["dist"][nid].append(None)
            series["dist"][nid].extend(seg)

    # ---- status segments + silence
    status_by = defaultdict(list)
    for r in sorted(status, key=lambda r: r.get("recv", 0)):
        status_by[r.get("node_id")].append((r["recv"] - t0, r.get("status")))
    status_segs, silent = {}, {}
    for nid in nodes:
        lst = status_by.get(nid, [])
        segs = []
        for i, (ts, st) in enumerate(lst):
            te = lst[i + 1][0] if i + 1 < len(lst) else t_end
            segs.append([r3(max(0, ts)), r3(te), st])
        status_segs[nid] = segs
        rbn = rb_by[nid]
        if rbn["last_t"] is not None and rbn["silent_s"] > 10 and (t_end - rbn["last_t"]) > 10:
            silent[nid] = [r3(rbn["last_t"]), r3(t_end)]

    ev_out_pre = [{"t": e["recv"] - t0, "title": e.get("title") or "", "node_id": e.get("node_id")}
                  for e in events if isinstance(e.get("recv"), (int, float))]

    # ---- onboard execution: the robot's own log (robot clock aligned to Henosync's)
    onboard = {}
    by_node = defaultdict(list)
    for r in robot_log:
        if r.get("node_id") in nodes and isinstance(r.get("t"), (int, float)):
            by_node[r["node_id"]].append(r)
    for nid, recs in by_node.items():
        recs.sort(key=lambda r: r["t"])
        # recv - sent = network latency + clock offset; the smallest is the best estimate
        offs = [r["recv"] - r["sent"] for r in recs
                if isinstance(r.get("recv"), (int, float)) and isinstance(r.get("sent"), (int, float))]
        off = min(offs) if offs else 0.0
        rt = (lambda o: lambda t: t + o - t0)(off)
        samples = [(rt(r["t"]), r["x"], r["y"], r.get("v") or 0.0, r.get("w") or 0.0)
                   for r in recs if r.get("kind") == "sample" and r.get("x") is not None]
        wps = [(rt(r["t"]), r.get("index"), r.get("link")) for r in recs if r.get("kind") == "waypoint"]
        segs, state, since = [], None, None
        for r in recs:
            k = r.get("kind")
            if k not in ("link_up", "link_lost", "link_restored"):
                continue
            ts = rt(r.get("last_heartbeat_t") or r["t"]) if k == "link_lost" else rt(r["t"])
            if state is not None:
                segs.append([r3(since), r3(ts), state])
            state, since = ("down" if k == "link_lost" else "up"), ts
        if state is not None:
            segs.append([r3(since), r3(max(t_end, since)), state])
        onboard[nid] = {"off": off, "aligned": bool(offs), "rt": rt, "recs": recs, "samples": samples,
                        "wps": wps, "segs": segs, "pose_topic": next((r.get("pose_topic") for r in reversed(recs) if r.get("kind") == "path_start"), None)}

    def _track_m(pts):
        return sum(math.dist((a[1], a[2]), (b[1], b[2])) for a, b in zip(pts, pts[1:]))

    # ---- link dropouts as Henosync saw them (status leaves "online"), cross-checked with the robot's log
    offline = []
    series_off, series_rob = {}, {}
    for nid in nodes:
        start = None
        wins = []
        for ts, st in status_by.get(nid, []):
            if st in ("degraded", "error") and start is None:
                start = ts
            elif st == "online" and start is not None:
                wins.append((start, ts, True))
                start = None
        if start is not None:
            wins.append((start, t_end, False))
        for a, b, restored in wins:
            simulated = any(e["node_id"] == nid and e["title"] == "Link Dropout Simulated" and a - 3 <= e["t"] <= a + 1
                            for e in ev_out_pre)
            g = grids[nid][0] if nid in grids else []
            vseg = [p for p in g if a <= p[0] <= b]
            w = {"node": nodes[nid]["name"], "node_id": nid, "start": r3(a), "end": r3(b), "dur": r3(b - a),
                 "restored": restored, "simulated": simulated, "vicon_m": r3(_track_m(vseg)),
                 "vicon_n": sum(1 for p in (T[nid]["pos"] if nid in T else []) if a <= p[0] <= b),
                 "robot_log": nid in onboard}
            if vseg:
                series_off.setdefault(nid, []).append([[r3(p[0]), r3(p[1]), r3(p[2])] for p in vseg])
            ob = onboard.get(nid)
            if ob:
                rt = ob["rt"]
                s_in = [x for x in ob["samples"] if a <= x[0] <= b]
                recs_in = [r for r in ob["recs"] if a <= rt(r["t"]) <= b]
                recv_in = [r["recv"] for r in recs_in if isinstance(r.get("recv"), (int, float))]
                down = next(([x, y] for x, y, st in ob["segs"] if st == "down" and x < b + 3 and y > a - 3), None)
                w.update({
                    "samples": len(s_in),
                    "cmd_samples": sum(1 for x in s_in if abs(x[3]) > CMD_V or abs(x[4]) > CMD_W),
                    "robot_m": r3(_track_m(s_in)),
                    "wps": [x[1] for x in ob["wps"] if a <= x[0] <= b],
                    "robot_down": down,
                    "records": len(recs_in),
                    "synced": r3(max(recv_in) - t0) if recv_in else None,
                    "pose_stale": sum(1 for r in recs_in if r.get("kind") == "pose_stale"),
                    "path_done": any(r.get("kind") == "path_done" for r in recs_in),
                    "pose_topic": ob["pose_topic"],
                    "aligned": ob["aligned"],
                })
                if s_in:
                    series_rob.setdefault(nid, []).append([[r3(x[0]), r3(x[1]), r3(x[2])] for x in s_in])
            offline.append(w)

    # ---- events
    ev_out = []
    for e in sorted(events, key=lambda e: e.get("recv", 0)):
        ev_out.append({"t": r3(e["recv"] - t0), "sev": e.get("severity") or "info", "title": e.get("title") or "",
                       "msg": e.get("message") or "", "node": name_of(e.get("node_id")), "node_id": e.get("node_id")})
    faults = [e for e in ev_out if e["sev"] in ("warning", "critical", "error")]

    # ======================================================================= findings
    F = []
    robots_named = lambda ids: ", ".join(rb_by[i]["name"] for i in ids)
    teleop_only = bool(steps) and all(("teleop" in (s["plugin"] + s["type"]).lower()) for s in steps)

    # 1. outages
    for nid, (ts, te) in silent.items():
        rbn = rb_by[nid]
        lost_for = te - ts
        sts = [t for t, st in status_by.get(nid, []) if st not in ("online", None)]
        lead = " It first reported '%s' at %s, %.0f s before going quiet." % (
            next(st for t, st in status_by[nid] if st not in ("online", None)), rel(sts[0]), ts - sts[0]) if sts and ts > sts[0] else ""
        resp = [e for e in faults if e["node_id"] == nid]
        resp_txt = (" System response: \"%s\"" % resp[0]["msg"]) if resp else ""
        F.append({"sev": "bad", "title": "%s dropped out at %s and never came back" % (rbn["name"], rel(ts)),
                  "body": "It sent no data for the remaining %s (%.0f%% of the run).%s%s" % (
                      dur(lost_for), 100 * lost_for / max(t_end, 1), lead, resp_txt),
                  "action": "Check %s's network link/power around that moment (its host is %s)." % (
                      rbn["name"], nodes[nid]["cfg"].get("host", "unknown")) if nodes[nid]["cfg"].get("host") else
                  "Check %s's network link/power around that moment." % rbn["name"]})
        if nid not in assigned and assigned:
            F.append({"sev": "warn", "title": "%s wasn't used by any step, but its loss still paused the mission" % rbn["name"],
                      "body": "Every step in this mission only commanded %s, yet the fault on an idle robot put the whole run into a paused, wait-for-operator state."
                              % robots_named(assigned),
                      "action": "If that's not intended, let the mission ignore faults from robots that no step uses (or mark robots as optional)."})
        # status log blind spot
        last_st = status_by[nid][-1][1] if status_by.get(nid) else None
        if last_st in ("online", "degraded"):
            F.append({"sev": "warn", "title": "status.jsonl never records %s as offline" % rbn["name"],
                      "body": "The event stream says the node was lost, but the status log's last entry for it is '%s'. Anyone reading the status log alone would miss the dropout." % last_st,
                      "action": "Have the status logger write a row when a node is declared lost/offline."})
    if faults and not silent:
        for e in faults[:5]:
            F.append({"sev": "bad" if e["sev"] != "warning" else "warn",
                      "title": "%s%s" % (e["title"], (" - " + e["node"]) if e["node"] else ""),
                      "body": "At %s: %s" % (rel(e["t"]), e["msg"])})

    # 1b. link dropouts - did the robot carry on by itself?
    for w in offline:
        how = "an operator-simulated dropout" if w["simulated"] else "a link dropout"
        span = "from %s to %s (%s)" % (rel(w["start"]), rel(w["end"]), dur(w["dur"])) if w["restored"] else \
               "from %s until the end of the run (%s) - never restored" % (rel(w["start"]), dur(w["dur"]))
        base = "Henosync lost its connection to %s %s, %s. " % (w["node"], span, how)
        vic = "Henosync's own VICON feed (independent of the robot link) recorded %d position samples and %.2f m of movement in that window." % (w["vicon_n"], w["vicon_m"] or 0)
        if not w["robot_log"]:
            F.append({"sev": "warn" if (w["vicon_m"] or 0) > 0.1 else "info",
                      "title": "%s: %s link dropout, no onboard log" % (w["node"], dur(w["dur"])),
                      "body": base + vic + " There is no robot-side log for this robot, so this can't be attributed to its onboard controller."})
            continue
        moved = (w["robot_m"] or 0) > 0.1 or (w["vicon_m"] or 0) > 0.1
        if w["samples"]:
            rob = "The robot's own log covers the window with %d samples; %d of them show its onboard controller commanding motion, it tracked %.2f m from its own pose" % (
                w["samples"], w["cmd_samples"], w["robot_m"] or 0)
            rob += (", and it reached waypoint%s %s while disconnected." % ("" if len(w["wps"]) == 1 else "s", ", ".join(str(i + 1) for i in w["wps"]))) if w["wps"] else ", reaching no waypoint while disconnected."
            if w["robot_down"]:
                rob += " Its own heartbeat watchdog saw Henosync go silent at %s and return at %s." % (rel(w["robot_down"][0]), rel(w["robot_down"][1]))
            if w["synced"] is not None:
                rob += " This log reached Henosync at %s%s." % (rel(w["synced"]), (", %s after the link came back" % dur(max(0, w["synced"] - w["end"]))) if w["restored"] else "")
            if not w["aligned"]:
                rob += " (Imported from the robot's disk log - robot clock not aligned to Henosync's.)"
            if moved and w["cmd_samples"]:
                F.append({"sev": "ok", "title": "%s kept executing its mission on the onboard controller while disconnected" % w["node"],
                          "body": base + vic + " " + rob})
            else:
                why = " It was steering by Henosync's relayed pose (%s), which stops with the link." % w["pose_topic"] if w["pose_topic"] and w["pose_topic"].endswith("vicon_pose") else \
                      (" Its pose went stale %d time(s)." % w["pose_stale"] if w["pose_stale"] else "")
                F.append({"sev": "warn", "title": "%s did not drive during the dropout" % w["node"],
                          "body": base + vic + " " + rob + why,
                          "action": "For onboard execution through a dropout, run vicon_pose_publisher.py and start the controller with --pose_topic /<ns>/henosync/onboard_pose."})
        elif w["restored"]:
            F.append({"sev": "bad", "title": "%s's log of the dropout never arrived" % w["node"],
                      "body": base + vic + " The link came back, but no robot-side records from the dropout window reached Henosync.",
                      "action": "Check henosync_controller.py was running; its records are also on the robot in ~/henosync_logs/."})
        else:
            F.append({"sev": "warn", "title": "%s's log of the dropout is still on the robot" % w["node"],
                      "body": base + vic + " The link never came back, so the robot couldn't send its log.",
                      "action": "Copy ~/henosync_logs/<file>.jsonl off the robot and import it: POST /api/runs/<run id>/robot-log (see tools/robot/README.md)."})

    # 2. idle time / lag between arrival and step close
    nav_steps = [s for s in steps if s["settle"] is not None and s["end"] is not None]
    lag_lines, lag_total = [], 0.0
    for s in nav_steps:
        after = (s["end"] - s["op_done"]) if s["op_done"] is not None else None
        waited = s["idle_after"] or 0
        if waited > 10 or (after is not None and after > 10):
            lag_total += max(waited, after or 0)
            hit = [e for e in faults if (s["op_done"] or s["settle"]) <= e["t"] <= s["end"]]
            why = (" A %s alert landed during this gap (%s at %s), and the mission was paused waiting for an operator - the likely cause."
                   % (hit[0]["sev"], hit[0]["title"], rel(hit[0]["t"]))) if hit else \
                  " No alert explains it."
            lag_lines.append("Step %d (%s): the robot came to rest at %s%s, but the step only closed at %s - %s later.%s" % (
                s["n"], s["name"], rel(s["settle"]),
                (", the controller reported success at %s" % rel(s["op_done"])) if s["op_done"] is not None else "",
                rel(s["end"]), dur(s["end"] - s["settle"]), why))
    if lag_lines:
        unexplained = [l for l in lag_lines if "No alert explains" in l]
        moving_s = len(moving_idx) * GRID_DT
        F.append({"sev": "warn",
                  "title": "The robot finished each move well before its step closed",
                  "body": "Actually driving: %s of %s (%.0f%%). The rest was waiting. " % (dur(moving_s), dur(t_end), 100 * moving_s / max(t_end, 1))
                          + " ".join(lag_lines),
                  "action": ("The %d s+ delay on a fault-free step suggests a fixed hold/settle timer or slow completion check in the runner - worth looking at." % int(min((s["end"] - s["settle"]) for s in nav_steps)))
                  if unexplained else "Consider letting the mission continue automatically (or after a short timeout) instead of waiting for an operator."})

    # 3. accuracy / path quality
    errs = [(s["n"], s["err"], s["target"]) for s in steps if s["err"] is not None]
    if errs:
        vals = [e[1] for e in errs]
        consistent = len(vals) >= 2 and max(vals) - min(vals) < 0.03
        F.append({"sev": "ok", "title": "Reached %s within %.2f m" % ("every target" if len(vals) > 1 else "the target", max(vals)),
                  "body": "Final error: %s. %s" % (", ".join("%s %.3f m" % (t or "step %d" % n, e) for n, e, t in errs),
                      "The stops are almost identical, which points to the controller's goal tolerance (about %.1f m) rather than random error - fine unless you need tighter precision." % (round(max(vals) * 5) / 5 if max(vals) > 0.1 else max(vals)) if consistent else "")})
    for s in nav_steps:
        if s["path_m"] and s["straight_m"] and s["straight_m"] > 0.5:
            ratio = s["path_m"] / s["straight_m"]
            s["straightness"] = ratio
    straight = [s for s in nav_steps if s.get("straightness")]
    if straight:
        worst = max(s["straightness"] for s in straight)
        F.append({"sev": "ok" if worst < 1.2 else "info",
                  "title": "Paths were %s" % ("essentially straight lines" if worst < 1.1 else "reasonably direct" if worst < 1.3 else "winding"),
                  "body": "; ".join("Step %d travelled %.2f m for a %.2f m straight-line gap (x%.2f)" % (s["n"], s["path_m"], s["straight_m"], s["straightness"]) for s in straight) + "."})
    for s in nav_steps:
        if s["path_m"] and s["travel_s"] is not None and s["settle"] and s["start"] is not None:
            s["cruise"] = s["path_m"] / max(s["settle"] - s["start"] - s["travel_s"], 0.1)
    cr = [s["cruise"] for s in nav_steps if s.get("cruise")]
    if cr:
        F.append({"sev": "info", "title": "Cruising speed about %.2f m/s" % (sum(cr) / len(cr)),
                  "body": "Each leg took %s of driving. Reaching a point 3 m away at this pace takes ~%.0f s, so travel is a small part of the total time."
                          % (" / ".join(dur(s["settle"] - s["start"]) for s in nav_steps if s.get("cruise")), 3 / (sum(cr) / len(cr)))})

    # 4. teleop
    if cmd:
        end_cmd = steps[-1]["end"] if steps and steps[-1]["end"] is not None else t_end
        segs = [(cmd[i][0], (cmd[i + 1][0] if i + 1 < len(cmd) else end_cmd), cmd[i][1], cmd[i][2]) for i in range(len(cmd))]
        tot = sum(b - a for a, b, _, _ in segs) or 1
        fwd = sum(b - a for a, b, l, w in segs if l > 0)
        rev = sum(b - a for a, b, l, w in segs if l < 0)
        spin = sum(b - a for a, b, l, w in segs if l == 0 and w != 0)
        stop = sum(b - a for a, b, l, w in segs if l == 0 and w == 0)
        changes = sum(1 for i in range(1, len(cmd)) if cmd[i][1:] != cmd[i - 1][1:])
        F.append({"sev": "info", "title": "Manual drive: %s of keyboard control" % dur(tot),
                  "body": "Forward %s (%.0f%%), reverse %s, turning on the spot %s, stopped %s. %s command changes (about one every %.1f s). Commands are all-or-nothing (max |%.1f|), as expected from arrow-key teleop."
                          % (dur(fwd), 100 * fwd / tot, dur(rev), dur(spin), dur(stop), changes, tot / max(changes, 1),
                             max(abs(c[1]) for c in cmd))})
        peak = max(abs(c[1]) for c in cmd)
        for rb in robots:
            if rb["assigned"] and rb["speed_p95"] and rb["speed_p95"] < 0.5 * peak:
                tb = "turtlebot" in rb["plugin"].lower()
                F.append({"sev": "info", "title": "%s never got near the commanded speed" % rb["name"],
                          "body": "Commanded up to %.1f m/s, but measured speed stayed at or below ~%.2f m/s. %s" % (
                              peak, rb["speed_p95"],
                              "A TurtleBot3 tops out around 0.2 m/s, so anything above that setting is just 'full speed'." if tb else
                              "The robot (or its driver) is clipping the command."),
                          "action": "Set the teleop max speed to what the robot can actually reach so the number on screen means something."})

    # 5. data completeness
    for rb in robots:
        if rb["assigned"] and not rb["pos"] and (rb["pos_source"] == "vicon"):
            F.append({"sev": "warn", "title": "No position data was recorded for %s" % rb["name"],
                      "body": "Its position source is Vicon but the Vicon object name is %s, so only battery and speed were logged. The path, distance and accuracy charts can't be drawn for this run." % (
                          "blank" if not rb["vicon_name"] else "'%s' (no matching samples arrived)" % rb["vicon_name"]),
                      "action": "Set the Vicon object name for this robot before the run."})
    # 6. telemetry health
    healthy = [rb for rb in robots if rb["rate_hz"] and rb["id"] not in silent]
    for rb in healthy:
        if rb["max_gap"] > 1.0:
            F.append({"sev": "warn", "title": "%s telemetry had a %.1f s gap" % (rb["name"], rb["max_gap"]),
                      "body": "Typical rate is %.0f Hz, but there was at least one pause of %.1f s between samples." % (rb["rate_hz"], rb["max_gap"])})
    if healthy and not [f for f in F if "gap" in f["title"]]:
        F.append({"sev": "ok", "title": "Telemetry was steady",
                  "body": "; ".join("%s ~%.0f Hz, longest pause %.2f s" % (rb["name"], rb["rate_hz"], rb["max_gap"]) for rb in healthy) +
                          ". No dropouts for these robots."})
    # 7. battery
    for rb in robots:
        b = rb["batt"]
        if not b or (not rb["assigned"] and len(robots) > 1 and b["jitter"] < 0.5):
            continue
        if b["end"] < 20:
            F.append({"sev": "warn", "title": "%s battery low (%.0f%%)" % (rb["name"], b["end"]), "body": "Charge before the next run."})
        elif b["jitter"] > 1.5:
            F.append({"sev": "info", "title": "%s battery reading is noisy (±%.1f points)" % (rb["name"], b["jitter"] / 2),
                      "body": "It bounces between %.1f%% and %.1f%% within a single %s run, so real drain can't be measured over a run this short. Treat the percentage as a rough guide." % (b["min"], b["max"], dur(t_end))})
        else:
            F.append({"sev": "ok", "title": "%s battery steady at ~%.0f%%" % (rb["name"], b["end"]), "body": "Moved %.1f points over the run." % abs(b["end"] - b["start"])})

    # ---- verdict
    n_done = sum(1 for s in steps if s["outcome"] == "completed")
    bad = [f for f in F if f["sev"] == "bad"]
    warn = [f for f in F if f["sev"] == "warn"]
    if not finished:
        level, chip = "warn", "Incomplete log"
    elif outcome == "completed":
        level, chip = ("warn", "Completed with issues") if (bad or warn) else ("ok", "Completed cleanly")
    elif outcome == "stopped" and teleop_only:
        level, chip = ("warn", "Ended by operator, with issues") if bad else ("ok", "Ended by operator")
    elif outcome == "stopped":
        level, chip = "warn", "Stopped before finishing"
    else:
        level, chip = "bad", outcome.capitalize()
    pieces = []
    if teleop_only:
        pieces.append("Manual drive session of %s, ended by the operator" % dur(t_end) if outcome == "stopped" else "Manual drive session of %s" % dur(t_end))
    elif steps:
        pieces.append("%s of %s completed" % (plural(n_done, "step"), len(steps)) if n_done != len(steps) else
                      "All %d step%s completed" % (len(steps), "" if len(steps) == 1 else "s"))
        if errs:
            pieces[-1] += " (arrived within %.2f m)" % max(e[1] for e in errs)
    moving_s = len(moving_idx) * GRID_DT
    tail = []
    if lag_lines and moving_s:
        tail.append("only %.0f%% of the %s was spent driving" % (100 * moving_s / max(t_end, 1), dur(t_end)))
    for nid, (ts, _) in silent.items():
        tail.append("%s dropped out at %s%s" % (rb_by[nid]["name"], rel(ts), ", pausing the mission" if any("paus" in e["msg"].lower() for e in faults) else ""))
    if any(f["title"].startswith("No position data") for f in F):
        tail.append("no position data was captured")
    offline_ok = [w for w in offline if w.get("cmd_samples") and ((w.get("robot_m") or 0) > 0.1 or (w.get("vicon_m") or 0) > 0.1)]
    if offline_ok:
        tail.insert(0, "%s drove %.2f m on its onboard controller while disconnected" % (
            offline_ok[0]["node"], sum(w["vicon_m"] or w["robot_m"] or 0 for w in offline_ok)))
    headline = pieces[0] if pieces else "Run %s" % outcome
    if tail:
        headline += " - but " + (tail[0] if len(tail) == 1 else ", ".join(tail[:-1]) + ", and " + tail[-1])
    headline += "."

    tiles = [{"label": "Duration", "value": dur(t_end), "sub": "outcome: %s" % outcome}]
    if steps:
        tiles.append({"label": "Steps done", "value": "%d / %d" % (n_done, len(steps)), "sub": ", ".join(sorted({s["name"] for s in steps})[:2]) if len(steps) > 1 else steps[0]["name"]})
    if moving_idx:
        tiles.append({"label": "Time spent driving", "value": "%.0f%%" % (100 * moving_s / max(t_end, 1)), "sub": "%s moving, %s waiting" % (dur(moving_s), dur(max(t_end - moving_s, 0))),
                      "level": "warn" if moving_s / max(t_end, 1) < 0.4 else "ok"})
    if errs:
        tiles.append({"label": "Arrival error", "value": "%.2f m" % (sum(e[1] for e in errs) / len(errs)), "sub": "worst %.3f m" % max(e[1] for e in errs)})
    tiles.append({"label": "Alerts", "value": str(len(faults)), "sub": ("%d critical" % sum(1 for e in faults if e["sev"] == "critical")) if faults else "none",
                  "level": "bad" if any(e["sev"] == "critical" for e in faults) else ("warn" if faults else "ok")})
    if cmd:
        tiles.insert(1, {"label": "Commands sent", "value": str(len(cmd)), "sub": "keyboard teleop"})
    cov = [s["coverage"] for s in steps if s["coverage"] is not None]
    if cov:
        tiles.append({"label": "Zone coverage", "value": "%.0f%%" % max(cov), "sub": "from the VICON trail"})
    if offline:
        moved = sum(w["vicon_m"] or 0 for w in offline)
        tiles.append({"label": "Disconnected", "value": dur(sum(w["dur"] for w in offline)),
                      "sub": "%.2f m driven meanwhile, %d waypoint(s)" % (moved, sum(len(w.get("wps") or []) for w in offline)),
                      "level": "ok" if offline_ok else "warn"})

    # ---- narrative
    N = [{"t": 0, "sev": "info", "text": "Run started - mission \"%s\"; robots: %s." % (meta.get("mission") or summ.get("mission") or "?", ", ".join(r["name"] for r in robots) or "none")}]
    for s in steps:
        if s["start"] is not None:
            N.append({"t": s["start"], "sev": "info", "text": "Step %d \"%s\" started%s." % (s["n"], s["name"], (" - %s -> %s" % (s["robot"], s["target"])) if s["target"] and s["robot"] else (" - %s" % s["robot"] if s["robot"] else ""))})
        if s["settle"] is not None and s["idle_after"] and s["idle_after"] > 1:
            N.append({"t": s["settle"], "sev": "ok", "text": "%s came to rest%s." % (s["robot"], (" %.3f m from %s" % (s["err"], s["target"])) if s["err"] is not None and s["target"] else "")})
        if s["op_done"] is not None and (s["settle"] is None or abs(s["op_done"] - s["settle"]) > 0.8):
            N.append({"t": s["op_done"], "sev": "info", "text": "Controller reported done%s." % ((": \"%s\"" % s["status_text"]) if s["status_text"] else "")})
        if s["end"] is not None:
            N.append({"t": s["end"], "sev": "ok" if s["outcome"] == "completed" else "warn", "text": "Step %d closed - %s%s." % (s["n"], s["outcome"], (" (%s)" % dur(s["duration"])) if s["duration"] else "")})
    step_marks = [x for s in steps for x in (s["start"], s["end"]) if x is not None]
    for e in ev_out:
        if e["title"].startswith("Operation ") and any(abs(e["t"] - m) < 1.5 for m in step_marks):
            continue
        N.append({"t": e["t"], "sev": {"critical": "bad", "error": "bad", "warning": "warn"}.get(e["sev"], "info"),
                  "text": "%s%s: %s" % (e["title"], (" (%s)" % e["node"]) if e["node"] else "", e["msg"])})
    for nid, lst in status_by.items():
        for i, (ts, st) in enumerate(lst):
            if st not in ("online", None) and not (i == 0 and False):
                N.append({"t": ts, "sev": "warn", "text": "%s status changed to \"%s\"." % (rb_by[nid]["name"], st)})
    if cmd:
        N.append({"t": cmd[0][0], "sev": "info", "text": "Operator began driving with the keyboard (%s sent)." % plural(len(cmd), "command")})
    for nid, ob in onboard.items():
        nm = nodes[nid]["name"]
        for a, b, st in ob["segs"]:
            if st == "down":
                N.append({"t": a, "sev": "warn", "text": "%s (robot log): last heartbeat from Henosync - link lost, onboard controller carries on." % nm})
                if b < t_end:
                    N.append({"t": b, "sev": "info", "text": "%s (robot log): Henosync heartbeat back after %s." % (nm, dur(b - a))})
        for t, idx, link in ob["wps"]:
            if link is False:
                N.append({"t": t, "sev": "ok", "text": "%s (robot log): reached waypoint %s on its own while disconnected." % (nm, (idx or 0) + 1)})
    for w in offline:
        if w.get("synced") is not None and w["records"]:
            N.append({"t": w["synced"], "sev": "info", "text": "%s's log of the dropout received by Henosync (%s)." % (w["node"], plural(w["records"], "record"))})
    N.append({"t": t_end, "sev": "ok" if outcome == "completed" else "info", "text": "Run ended - outcome \"%s\"." % outcome})
    N.sort(key=lambda x: x["t"])
    for x in N:
        x["t"] = r3(x["t"])

    # ---- chart captions (headline of each chart)
    cap = {"gantt": "When each step ran, how healthy each robot was, and when alerts fired",
           "map": "Where the robots went (Vicon coordinates, metres)", "speed": "How fast each robot was moving",
           "dist": "Distance to the current target", "rate": "Telemetry arriving from each robot, second by second",
           "batt": "Battery level", "cmd": "What the operator told the robot to do"}
    bursts = 0
    for nid in assigned:
        if nid in grids:
            sp = grids[nid][1]
            bursts += sum(1 for i in range(1, len(sp)) if sp[i] > MOVE_V and sp[i - 1] <= MOVE_V)
    if bursts and moving_idx:
        cap["speed"] = "%s moved in %s - parked the rest of the time" % (", ".join(rb_by[i]["name"] for i in assigned if i in grids), plural(bursts, "burst"))
        if teleop_only:
            cap["speed"] = "Speed over time"
    if any(s["idle_after"] and s["idle_after"] > 5 for s in steps):
        cap["dist"] = "Distance to target drops to ~%.2f m, then sits flat while the step stays open" % (sum(e[1] for e in errs) / len(errs) if errs else 0)
    if silent:
        cap["rate"] = "%s went silent at %s" % (", ".join(rb_by[n]["name"] for n in silent), ", ".join(rel(v[0]) for v in silent.values()))
        cap["gantt"] = "%s lost at %s; the mission paused" % (", ".join(rb_by[n]["name"] for n in silent), rel(list(silent.values())[0][0])) if any("paus" in e["msg"].lower() for e in faults) else cap["gantt"]
    if cmd:
        cap["cmd"] = "Operator commands: forward/back and turning"

    # ---- files
    files = []
    for fn in FILE_ORDER:
        p = d / fn
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        lines = txt.splitlines()
        full = len(txt) <= 20000
        prev = txt if full else "\n".join(lines[:30])
        info = ""
        if fn == "summary.json":
            info = "Outcome \"%s\"; %s recorded." % (outcome, plural(len(results), "step result"))
        elif fn == "meta.json":
            info = "%s, %s (%s), %s, %s." % (plural(len(meta_steps), "step"), plural(len(nodes), "robot"), ", ".join(r["name"] for r in robots),
                                              plural(len(meta.get("markers") or []), "map marker"), plural(len(meta.get("zones") or []), "zone"))
        elif fn == "steps.jsonl":
            info = "%s start/end records." % len(steps_log)
        elif fn == "operations.jsonl":
            info = "%s status updates; states seen: %s." % (len(ops), ", ".join("%s x%d" % kv for kv in Counter((o.get("status") or {}).get("state") for o in ops).items()))
        elif fn == "events.jsonl":
            info = "%s: %s." % (plural(len(ev_out), "event"), ", ".join("%d %s" % (v, k) for k, v in Counter(e["sev"] for e in ev_out).items()) or "none")
        elif fn == "status.jsonl":
            info = "%s across %s." % (plural(len(status), "status record"), plural(len(status_by), "robot"))
        elif fn == "robot.jsonl":
            late = sum(1 for r in robot_log if r.get("link") is False or r.get("kind") == "link_lost")
            info = "%s from %s; %d made while disconnected." % (plural(len(robot_log), "record"), plural(len(onboard), "robot"), late)
        elif fn == "telemetry.jsonl":
            info = "%s samples from %s; %s." % (format(len(tele), ","), plural(len(T), "robot"), "; ".join("%s ~%.0f Hz" % (rb["name"], rb["rate_hz"]) for rb in robots if rb["rate_hz"]))
            if bad_tele:
                info += " %d unreadable lines skipped." % bad_tele
        files.append({"name": fn, "size": p.stat().st_size, "lines": len(lines), "desc": FILE_DESC[fn], "info": info,
                      "preview": prev, "truncated": not full, "shown_lines": len(prev.splitlines())})

    targets = []
    for s in steps:
        if s["tx"] is not None:
            targets.append({"name": s["target"] or "Step %d" % s["n"], "x": s["tx"], "y": s["ty"], "step": s["n"]})
    # waypoints not used as targets still drawn lightly
    used = {t["name"] for t in targets}
    for m in markers.values():
        if m.get("map_mode") == "vicon" and m.get("name") not in used:
            targets.append({"name": m["name"], "x": m["lon"], "y": m["lat"], "step": None})

    zones = []
    for z in meta.get("zones") or []:
        if z.get("map_mode") != "vicon":
            continue
        if z.get("center") and z.get("radius_m"):
            c, rad = z["center"], z["radius_m"]
            pts = [[c["lon"] + rad * math.cos(2 * math.pi * i / 32), c["lat"] + rad * math.sin(2 * math.pi * i / 32)] for i in range(32)]
        else:
            pts = [[q["lon"], q["lat"]] for q in z.get("points") or []]
        if len(pts) >= 3:
            zones.append({"name": z.get("name") or "", "pts": [[r3(x), r3(y)] for x, y in pts]})
    series["offline"] = series_off
    series["robot"] = series_rob
    onboard_rows = {nid: {"segs": ob["segs"], "wps": [[r3(t), i, l] for t, i, l in ob["wps"]]} for nid, ob in onboard.items()}

    for s in steps:
        for k in ("start", "end", "duration", "settle", "idle_after", "op_done", "travel_s", "path_m", "straight_m", "err", "tx", "ty", "fx", "fy", "straightness", "cruise"):
            if k in s:
                s[k] = r3(s[k]) if isinstance(s[k], (int, float)) else s[k]
    for rb in robots:
        for k in ("rate_hz", "first_t", "last_t", "silent_s", "max_gap", "speed_p95"):
            rb[k] = r3(rb[k])
    for e in ev_out:
        pass

    return {
        "id": d.name, "mission": meta.get("mission") or summ.get("mission") or d.name, "started": t0, "duration": r3(t_end),
        "finished": finished, "outcome": outcome, "teleop": teleop_only,
        "verdict": {"level": level, "chip": chip, "headline": headline}, "tiles": tiles, "robots": robots, "steps": steps,
        "narrative": N, "findings": F, "events": ev_out, "status_segs": status_segs, "silent": silent,
        "series": series, "targets": targets, "captions": cap, "files": files,
        "zones": zones, "offline": offline, "onboard": onboard_rows,
        "moving_s": r3(moving_s), "n_faults": len(faults),
        "assigned": sorted(assigned),
    }


# ----------------------------------------------------------------------------- across runs
def compare_runs(runs):
    out = []
    if len(runs) < 2:
        return out
    for a, b in zip(runs, runs[1:]):
        gap = b["started"] - (a["started"] + a["duration"])
        ra = {r["id"]: r for r in a["robots"]}
        rb_ = {r["id"]: r for r in b["robots"]}
        # fleet change
        na, nb = {r["name"] for r in a["robots"]}, {r["name"] for r in b["robots"]}
        if na != nb:
            out.append({"sev": "info", "title": "Fleet changed between runs",
                        "body": "%s -> %s (now %s)." % (", ".join(sorted(na)) or "none", ", ".join(sorted(nb)) or "none", plural(len(nb), "robot"))})
        for nid, r2 in rb_.items():
            r1 = ra.get(nid)
            if not r1:
                continue
            if r1["vicon_name"] != r2["vicon_name"]:
                out.append({"sev": "ok" if r2["vicon_name"] else "warn", "title": "%s's Vicon object name changed" % r2["name"],
                            "body": "Blank -> \"%s\", which is why only the later run has position data." % r2["vicon_name"] if (not r1["vicon_name"] and r2["vicon_name"]) else
                                    "\"%s\" -> \"%s\"." % (r1["vicon_name"], r2["vicon_name"])})
            if r1["batt"] and r2["batt"] and abs(r1["batt"]["end"] - r2["batt"]["start"]) >= 5:
                out.append({"sev": "info", "title": "%s battery: %.0f%% -> %.0f%% between runs" % (r2["name"], r1["batt"]["end"], r2["batt"]["start"]),
                            "body": "%s passed between the end of one run and the start of the next. Either it drained while powered on (or was swapped/charged), or the percentage is unreliable - it already bounced by about %.0f points inside a single run." % (dur(max(gap, 0)), max(r1["batt"]["jitter"], r2["batt"]["jitter"]))})
            if r1["speed_p95"] and r2["speed_p95"] and abs(r1["speed_p95"] - r2["speed_p95"]) < 0.05 and r1["assigned"] and r2["assigned"]:
                out.append({"sev": "info", "title": "%s hit the same top speed in both runs (~%.2f m/s)" % (r2["name"], (r1["speed_p95"] + r2["speed_p95"]) / 2),
                            "body": "Despite different modes (%s vs %s), measured speed topped out at about the same value, so that is the robot's practical ceiling." % (
                                "teleop" if a["teleop"] else "navigation", "teleop" if b["teleop"] else "navigation")})
    with_faults = [r for r in runs if r["n_faults"]]
    if with_faults:
        out.append({"sev": "warn", "title": "%d of %d runs raised alerts" % (len(with_faults), len(runs)),
                    "body": "; ".join("%s: %s" % (r["id"][:16], ", ".join(sorted({e['title'] + (' (' + e['node'] + ')' if e['node'] else '') for e in r['events'] if e['sev'] in ('warning', 'critical', 'error')}))) for r in with_faults)})
    return out


# ----------------------------------------------------------------------------- main
def find_runs(root):
    root = Path(root).expanduser()
    if (root / "meta.json").exists() or (root / "summary.json").exists() or (root / "telemetry.jsonl").exists():
        return [root]
    return sorted(p for p in root.iterdir() if p.is_dir() and any((p / f).exists() for f in FILE_ORDER)) if root.exists() else []


def main():
    ap = argparse.ArgumentParser(description="Build a human-readable HTML report from Henosync mission-run logs.")
    ap.add_argument("runs_dir", nargs="?", default=str(Path.home() / ".henosync" / "runs"))
    ap.add_argument("-o", "--output", default="henosync_report.html")
    ap.add_argument("--last", type=int, default=0, help="only the most recent N runs")
    ap.add_argument("--open", action="store_true", help="open the report in your browser when done")
    a = ap.parse_args()

    dirs = find_runs(a.runs_dir)
    if a.last:
        dirs = dirs[-a.last:]
    if not dirs:
        sys.exit("No run folders found in %s" % a.runs_dir)
    runs = [analyse_run(d) for d in dirs]
    runs.sort(key=lambda r: r["started"])
    names = sorted({rb["name"] for r in runs for rb in r["robots"]})
    for r in runs:
        for rb in r["robots"]:
            rb["slot"] = names.index(rb["name"]) % 8
    data = {"runs": runs, "cross": compare_runs(runs), "source": str(Path(a.runs_dir).expanduser()),
            "generated": datetime.now().timestamp()}
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    Path(a.output).write_text(HTML.replace("/*__DATA__*/null", blob), encoding="utf-8")

    # terminal summary
    print("\nHenosync report - %s\n" % plural(len(runs), "run"))
    for r in runs:
        print("* %s  [%s]" % (r["id"], r["verdict"]["chip"]))
        print("  %s" % r["verdict"]["headline"])
        for f in r["findings"]:
            if f["sev"] in ("bad", "warn"):
                print("    %s %s" % ("!!" if f["sev"] == "bad" else " !", f["title"]))
        print()
    print("Wrote %s (%.0f KB)" % (Path(a.output).resolve(), Path(a.output).stat().st_size / 1024))
    if a.open:
        webbrowser.open(Path(a.output).resolve().as_uri())


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Henosync Run Report</title>
<style>
:root{color-scheme:light;
 --bg:#f6f6f4;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#7a7873;--line:#e4e3de;--grid:#ebeae6;--tint:#f0efeb;
 --s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s6:#008300;--s7:#6250d6;--s8:#e34948;
 --ok:#1a7f37;--warn:#9a5b00;--bad:#c62828;--info:#2a78d6;
 --ok-bg:#e3f4e8;--warn-bg:#fdf0d6;--bad-bg:#fbe4e3;--info-bg:#e4eefb;}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;
 --bg:#121211;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#98968e;--line:#2d2d2b;--grid:#262624;--tint:#222220;
 --s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;
 --ok:#4cc16f;--warn:#f0b04a;--bad:#f07b7a;--info:#6aa6ef;
 --ok-bg:#16301f;--warn-bg:#3a2b0e;--bad-bg:#3d1b1a;--info-bg:#15283f;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px 64px}
header{padding:28px 0 8px}h1{font-size:22px;margin:0 0 2px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13px}
nav{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0 20px;border-bottom:1px solid var(--line);padding-bottom:12px}
nav button{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--surface);color:var(--ink2);padding:6px 12px;border-radius:999px;cursor:pointer}
nav button[aria-current=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
section{margin:28px 0}h2{font-size:17px;margin:0 0 12px;letter-spacing:-.005em}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:600;padding:3px 10px;border-radius:999px}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.info{color:var(--info)}
.chip.ok{background:var(--ok-bg)}.chip.warn{background:var(--warn-bg)}.chip.bad{background:var(--bad-bg)}.chip.info{background:var(--info-bg)}
.verdict{display:flex;flex-direction:column;gap:10px}.verdict .hl{font-size:19px;line-height:1.35;font-weight:600;letter-spacing:-.01em}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:14px}
.tile{background:var(--tint);border-radius:10px;padding:10px 12px}.tile .l{font-size:12px;color:var(--muted)}.tile .v{font-size:22px;font-weight:650;letter-spacing:-.01em}.tile .s{font-size:12px;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.finding{display:grid;grid-template-columns:28px 1fr;gap:4px 8px;padding:12px 0;border-top:1px solid var(--line)}.finding:first-child{border-top:0}
.finding .ic{font-weight:700;text-align:center;font-size:16px;line-height:22px}.finding h3{font-size:15px;margin:0}.finding p{margin:3px 0 0;color:var(--ink2);font-size:14px}
.finding .act{margin-top:6px;font-size:13.5px;color:var(--ink);background:var(--tint);border-radius:8px;padding:6px 10px}
.story{list-style:none;margin:0;padding:0}.story li{display:grid;grid-template-columns:54px 14px 1fr;gap:8px;padding:5px 0;font-size:14px}
.story .t{font-variant-numeric:tabular-nums;color:var(--muted);text-align:right}.story .dot{width:10px;height:10px;border-radius:50%;margin-top:6px;background:var(--muted)}
.dot.ok{background:var(--ok)}.dot.warn{background:var(--warn)}.dot.bad{background:var(--bad)}.dot.info{background:var(--info)}
.story li.bad{font-weight:600}
.chart h3{font-size:14.5px;margin:0 0 2px}.chart .legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:var(--ink2);margin:4px 0}.sw{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.chart{margin-bottom:14px}.chart svg{display:block;max-width:100%}
svg text{fill:var(--muted);font-size:11px;font-family:inherit}svg .lab{fill:var(--ink2)}svg .grid{stroke:var(--grid);stroke-width:1}
svg .axis{stroke:var(--line)}svg .cur{stroke:var(--ink);stroke-width:1;opacity:.55;pointer-events:none}
.band{fill:var(--tint);opacity:.7}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{text-align:left;padding:7px 8px;border-top:1px solid var(--line);white-space:nowrap}th{font-weight:600;color:var(--muted);font-size:12px;border-top:0}
.scroll{overflow-x:auto}tr.click{cursor:pointer}tr.click:hover{background:var(--tint)}
.scrub{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);margin-bottom:12px}
.scrub .row{display:flex;gap:12px;align-items:center}.scrub input{flex:1;accent-color:var(--s1)}.scrub .rd{font-size:12.5px;color:var(--ink2);margin-top:4px;display:flex;gap:16px;flex-wrap:wrap}
.scrub .tt{font-variant-numeric:tabular-nums;font-weight:600;min-width:46px}
.files{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
.file h3{font-size:14.5px;margin:0;font-family:ui-monospace,Consolas,monospace}.file .m{font-size:12px;color:var(--muted)}.file p{margin:6px 0;font-size:13.5px;color:var(--ink2)}
.file .learn{font-size:13.5px}details summary{cursor:pointer;font-size:13px;color:var(--info);margin-top:6px}
pre{background:var(--tint);padding:10px;border-radius:8px;overflow:auto;max-height:320px;font-size:12px;line-height:1.45;margin:6px 0 0}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--bg);padding:6px 9px;border-radius:8px;font-size:12px;z-index:50;display:none;max-width:280px;line-height:1.4}
.note{color:var(--muted);font-size:13px;padding:18px;text-align:center}
.two{display:grid;grid-template-columns:1fr;gap:14px}
@media(min-width:900px){.two.map{grid-template-columns:1.1fr .9fr}}
.hatch{fill:url(#hat)}
</style></head>
<body><div class="wrap">
<header><h1>Henosync Run Report</h1><div class="sub" id="sub"></div></header>
<nav id="nav"></nav>
<main id="main"></main>
</div><div id="tip"></div>
<svg width="0" height="0" style="position:absolute"><defs>
<pattern id="hat" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="var(--bad-bg)"/><line x1="0" y1="0" x2="0" y2="6" stroke="var(--bad)" stroke-width="2"/></pattern>
</defs></svg>
<script>
const D = /*__DATA__*/null;
const esc = s => String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmtT = t => { t=Math.max(0,t); return Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0'); };
const fmtDur = s => s==null?'-': s<60? Math.round(s)+' s' : Math.floor(s/60)+'m '+String(Math.round(s%60)).padStart(2,'0')+'s';
const fmtClock = e => new Date(e*1000).toLocaleString([], {weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
const ICON = {ok:'✓',warn:'⚠',bad:'✕',info:'ℹ'};
const col = slot => 'var(--s'+(slot+1)+')';
const tip = document.getElementById('tip');
function showTip(html,e){tip.innerHTML=html;tip.style.display='block';const w=tip.offsetWidth;let x=e.clientX+14;if(x+w>innerWidth-8)x=e.clientX-w-14;tip.style.left=x+'px';tip.style.top=(e.clientY+14)+'px';}
function hideTip(){tip.style.display='none';}
document.addEventListener('pointerover',e=>{const el=e.target.closest&&e.target.closest('[data-tip]');if(el)showTip(el.dataset.tip,e);});
document.addEventListener('pointermove',e=>{if(tip.style.display==='block'&&e.target.closest&&e.target.closest('[data-tip]'))showTip(e.target.closest('[data-tip]').dataset.tip,e);});
document.addEventListener('pointerout',e=>{if(e.target.closest&&e.target.closest('[data-tip]'))hideTip();});

// ---- shared time cursor
const cur = {t:0, subs:[]};
function setT(t){cur.t=t;cur.subs.forEach(f=>f(t));}
let renderers = [];   // re-run on resize
function niceStep(range,n){const raw=range/n,p=Math.pow(10,Math.floor(Math.log10(raw))),f=raw/p;return (f<1.5?1:f<3?2:f<7?5:10)*p;}
function ticks(a,b,n){const st=niceStep(b-a,n),out=[];for(let v=Math.ceil(a/st)*st;v<=b+1e-9;v+=st)out.push(+v.toFixed(6));return out;}
function xTicks(xmax){const cands=[5,10,15,30,60,120,300,600,1800];const st=cands.find(c=>xmax/c<=8)||3600;const o=[];for(let t=0;t<=xmax;t+=st)o.push(t);return o;}
function valueAt(pts,t,step){let lo=0,hi=pts.length-1,r=-1;while(lo<=hi){const m=(lo+hi)>>1;if(pts[m]&&pts[m][0]<=t){r=m;lo=m+1}else hi=m-1}
  if(r<0)return null;let p=pts[r];if(!p)return null;if(t-p[0]>2.5)return null;return p;}
function cleanPts(pts){return pts.filter(p=>p);}

function lineChart(host,o){
  const W=Math.max(300,host.clientWidth),H=o.h||180,m={l:44,r:12,t:8,b:22},iw=W-m.l-m.r,ih=H-m.t-m.b;
  const x=t=>m.l+t/o.xmax*iw,y=v=>m.t+ih-(v-o.ymin)/(o.ymax-o.ymin)*ih;
  let s=`<svg width="${W}" height="${H}" role="img" aria-label="${esc(o.aria||o.title||'chart')}">`;
  (o.bands||[]).forEach(b=>{s+=`<rect class="band" x="${x(b.t0)}" y="${m.t}" width="${Math.max(0,x(b.t1)-x(b.t0))}" height="${ih}" data-tip="${esc(b.label)}"/>`;});
  ticks(o.ymin,o.ymax,4).forEach(v=>{s+=`<line class="grid" x1="${m.l}" x2="${W-m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l-6}" y="${y(v)+4}" text-anchor="end">${(o.yfmt||(v=>v))(v)}</text>`;});
  xTicks(o.xmax).forEach(t=>{s+=`<text x="${x(t)}" y="${H-6}" text-anchor="middle">${fmtT(t)}</text>`;});
  s+=`<line class="axis" x1="${m.l}" x2="${W-m.r}" y1="${m.t+ih}" y2="${m.t+ih}"/>`;
  o.series.forEach(se=>{
    let d='',pen=false,prev=null;
    se.pts.forEach(p=>{ if(!p){pen=false;prev=null;return;}
      if(se.step&&prev!==null){d+=`L${x(p[0]).toFixed(1)},${y(prev).toFixed(1)}`;}
      d+=(pen?'L':'M')+x(p[0]).toFixed(1)+','+y(p[1]).toFixed(1);pen=true;prev=p[1];});
    s+=`<path d="${d}" fill="none" style="stroke:${se.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" ${se.dash?'stroke-dasharray="5 4"':''}/>`;
  });
  s+=`<line class="cur" y1="${m.t}" y2="${m.t+ih}" x1="0" x2="0"/><rect class="hit" x="${m.l}" y="${m.t}" width="${iw}" height="${ih}" fill="transparent"/></svg>`;
  host.innerHTML=s;
  const svg=host.firstChild,line=svg.querySelector('.cur'),hit=svg.querySelector('.hit');
  const upd=t=>{line.setAttribute('x1',x(t));line.setAttribute('x2',x(t));};
  cur.subs.push(upd);upd(cur.t);
  const hover=e=>{const r=svg.getBoundingClientRect();const t=Math.min(o.xmax,Math.max(0,(e.clientX-r.left-m.l)/iw*o.xmax));setT(t);
    const rows=o.series.map(se=>{const p=valueAt(se.pts.filter(q=>q),t);return `<div><span class="sw" style="background:${se.color}"></span>${esc(se.name)}: <b>${p?(o.vfmt||(v=>v.toFixed(2)))(p[1]):'no data'}</b></div>`;}).join('');
    showTip(`<div>${fmtT(t)}</div>${rows}`,e);};
  hit.addEventListener('pointermove',hover);hit.addEventListener('pointerdown',hover);hit.addEventListener('pointerleave',hideTip);
}
function legend(items){return items.length>1?`<div class="legend">${items.map(i=>`<span><span class="sw" style="background:${i.color}"></span>${esc(i.name)}</span>`).join('')}</div>`:'';}

function gantt(host,R){
  const rows=[{k:'steps',label:'Steps'}];R.robots.forEach(r=>{rows.push({k:r.id,label:r.name,robot:r});if(R.onboard[r.id])rows.push({k:'ob',label:r.name+' (own)',robot:r});});rows.push({k:'ev',label:'Alerts'});
  const W=Math.max(320,host.clientWidth),L=78,rh=28,H=rows.length*rh+26,iw=W-L-10,xmax=Math.max(R.duration,1),x=t=>L+t/xmax*iw;
  let s=`<svg width="${W}" height="${H}" role="img" aria-label="Run timeline">`;
  xTicks(xmax).forEach(t=>{s+=`<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="0" y2="${rows.length*rh}"/><text x="${x(t)}" y="${H-6}" text-anchor="middle">${fmtT(t)}</text>`;});
  s+=`<rect class="bg" x="${L}" y="0" width="${iw}" height="${rows.length*rh}" fill="transparent"/>`;
  rows.forEach((r,i)=>{const y0=i*rh;s+=`<text class="lab" x="${L-8}" y="${y0+rh/2+4}" text-anchor="end">${esc(r.label)}</text>`;
    if(r.k==='steps'){R.steps.forEach(st=>{if(st.start==null)return;const e=st.end==null?R.duration:st.end,w=Math.max(2,x(e)-x(st.start));
      const tp=`<b>Step ${st.n}: ${esc(st.name)}</b><br>${fmtT(st.start)} → ${fmtT(e)} (${fmtDur(st.duration)})<br>${esc(st.outcome)}${st.settle!=null?`<br>Robot at rest from ${fmtT(st.settle)}`:''}`;
      s+=`<rect x="${x(st.start)}" y="${y0+4}" width="${w}" height="${rh-8}" rx="4" style="fill:var(--s1)" opacity=".85" data-tip="${esc(tp)}"/>`;
      if(st.settle!=null&&st.settle<e)s+=`<rect x="${x(st.settle)}" y="${y0+4}" width="${x(e)-x(st.settle)}" height="${rh-8}" rx="4" fill="url(#hat)" opacity=".0"/>`;
      if(w>70)s+=`<text x="${x(st.start)+6}" y="${y0+rh/2+4}" style="fill:#fff;font-weight:600">${esc('Step '+st.n)}</text>`;
      if(st.settle!=null&&st.idle_after>1){s+=`<rect x="${x(st.settle)}" y="${y0+4}" width="${Math.max(0,x(e)-x(st.settle))}" height="${rh-8}" rx="4" style="fill:var(--surface)" opacity=".55" data-tip="${esc(`<b>Waiting</b><br>Robot already at rest; step open for ${fmtDur(st.idle_after)} more`)}"/>`;}
    });}
    else if(r.k==='ob'){const ob=R.onboard[r.robot.id];ob.segs.forEach(([a,b,st])=>{const up=st==='up';
        s+=`<rect ${up?'style="fill:var(--ok)" opacity=".35"':'class="hatch"'} x="${x(a)}" y="${y0+8}" width="${Math.max(1,x(b)-x(a))}" height="${rh-16}" rx="3" data-tip="${esc(`<b>${r.robot.name}, robot's own log</b><br>${up?'Henosync heartbeat received':'No heartbeat from Henosync - driving on its own'}<br>${fmtT(a)} → ${fmtT(b)} (${fmtDur(b-a)})`)}"/>`;});
      ob.wps.forEach(([t,i,l])=>{s+=`<circle cx="${x(t)}" cy="${y0+rh/2}" r="4" style="fill:${l===false?'var(--warn)':'var(--ink2)'};stroke:var(--surface)" stroke-width="1.5" data-tip="${esc(`<b>Waypoint ${(i||0)+1} reached</b> (${fmtT(t)})${l===false?'<br>while disconnected':''}`)}"/>`;});}
    else if(r.k==='ev'){R.events.filter(e=>!(e.title.startsWith('Operation ')&&e.sev==='info')).forEach(e=>{const c=e.sev==='critical'||e.sev==='error'?'var(--bad)':e.sev==='warning'?'var(--warn)':'var(--info)';const cx=x(e.t),cy=y0+rh/2;
      s+=`<path d="M${cx},${cy-8}L${cx+8},${cy}L${cx},${cy+8}L${cx-8},${cy}Z" style="fill:${c};stroke:var(--surface)" stroke-width="2" data-tip="${esc(`<b>${e.title}</b> (${fmtT(e.t)})<br>${e.msg}`)}"/>`;});}
    else{ (R.status_segs[r.k]||[]).forEach(g=>{let [a,b,st]=g;const sil=R.silent[r.k];if(sil&&b>sil[0]&&a<sil[0]){b=sil[0];}
        if(sil&&a>=sil[0])return;const c=st==='online'?'var(--ok)':st==='degraded'?'var(--warn)':'var(--bad)';
        s+=`<rect x="${x(a)}" y="${y0+8}" width="${Math.max(1,x(b)-x(a))}" height="${rh-16}" rx="3" style="fill:${c}" opacity=".7" data-tip="${esc(`<b>${r.label}</b>: ${st}<br>${fmtT(a)} → ${fmtT(b)}`)}"/>`;});
      if(!(R.status_segs[r.k]||[]).length&&r.robot.last_t!=null){s+=`<rect x="${x(r.robot.first_t)}" y="${y0+8}" width="${x(Math.min(r.robot.last_t,xmax))-x(r.robot.first_t)}" height="${rh-16}" rx="3" style="fill:var(--ok)" opacity=".7"/>`;}
      const sil=R.silent[r.k];if(sil)s+=`<rect class="hatch" x="${x(sil[0])}" y="${y0+8}" width="${x(sil[1])-x(sil[0])}" height="${rh-16}" rx="3" data-tip="${esc(`<b>${r.label}</b>: no data<br>${fmtT(sil[0])} → ${fmtT(sil[1])} (${fmtDur(sil[1]-sil[0])})`)}"/>`;
    }});
  s+=`<line class="cur" y1="0" y2="${rows.length*rh}" x1="0" x2="0"/></svg>`;host.innerHTML=s;
  const svg=host.firstChild,line=svg.querySelector('.cur'),bg=svg.querySelector('.bg');
  const upd=t=>{line.setAttribute('x1',x(t));line.setAttribute('x2',x(t));};cur.subs.push(upd);upd(cur.t);
  const mv=e=>{const r=svg.getBoundingClientRect();setT(Math.min(xmax,Math.max(0,(e.clientX-r.left-L)/iw*xmax)));};
  bg.addEventListener('pointermove',mv);bg.addEventListener('pointerdown',mv);
}

function mapChart(host,R){
  const ids=Object.keys(R.series.path);
  if(!ids.length){host.innerHTML='<div class="note">No position data was recorded in this run.</div>';return;}
  let xs=[],ys=[];ids.forEach(i=>R.series.path[i].forEach(p=>{xs.push(p[1]);ys.push(p[2]);}));R.targets.forEach(t=>{xs.push(t.x);ys.push(t.y);});R.zones.forEach(z=>z.pts.forEach(p=>{xs.push(p[0]);ys.push(p[1]);}));
  const pad=.5,x0=Math.min(...xs)-pad,x1=Math.max(...xs)+pad,y0=Math.min(...ys)-pad,y1=Math.max(...ys)+pad;
  const W=Math.min(Math.max(300,host.clientWidth),640),sc=(W-50)/(x1-x0),H=Math.max(220,Math.min(460,(y1-y0)*sc+30)),k=Math.min(sc,(H-30)/(y1-y0));
  const X=v=>40+(v-x0)*k,Y=v=>H-24-(v-y0)*k;
  let s=`<svg width="${W}" height="${H}" role="img" aria-label="Map of robot paths">`;
  ticks(x0,x1,6).forEach(v=>{s+=`<line class="grid" x1="${X(v)}" x2="${X(v)}" y1="6" y2="${H-24}"/><text x="${X(v)}" y="${H-8}" text-anchor="middle">${v}</text>`;});
  ticks(y0,y1,6).forEach(v=>{s+=`<line class="grid" y1="${Y(v)}" y2="${Y(v)}" x1="40" x2="${W-6}"/><text x="34" y="${Y(v)+4}" text-anchor="end">${v}</text>`;});
  s+=`<text x="${W-6}" y="${H-8}" text-anchor="end">x (m)</text><text x="4" y="12">y (m)</text>`;
  R.zones.forEach(z=>{s+=`<polygon points="${z.pts.map(p=>X(p[0]).toFixed(1)+','+Y(p[1]).toFixed(1)).join(' ')}" style="fill:var(--info-bg);stroke:var(--info)" stroke-width="1.5" stroke-dasharray="5 3" data-tip="<b>Zone</b>: ${esc(z.name)}"/><text class="lab" x="${X(z.pts[0][0])+4}" y="${Y(z.pts[0][1])-4}">${esc(z.name)}</text>`;});
  R.targets.forEach(t=>{const used=t.step!=null;s+=`<g data-tip="<b>${esc(t.name)}</b><br>(${t.x.toFixed(2)}, ${t.y.toFixed(2)}) m"><circle cx="${X(t.x)}" cy="${Y(t.y)}" r="${used?11:8}" fill="none" stroke="var(--ink2)" stroke-width="${used?2:1}" ${used?'':'stroke-dasharray="3 3"'}/><circle cx="${X(t.x)}" cy="${Y(t.y)}" r="2.5" style="fill:var(--ink2)"/><text class="lab" x="${X(t.x)+14}" y="${Y(t.y)+4}">${esc(t.name)}</text></g>`;});
  R.robots.forEach(rb=>{const p=R.series.path[rb.id];if(!p)return;const c=col(rb.slot);
    s+=`<path d="${p.map((q,i)=>(i?'L':'M')+X(q[1]).toFixed(1)+','+Y(q[2]).toFixed(1)).join('')}" fill="none" style="stroke:${c}" stroke-width="2" opacity=".28" stroke-linejoin="round"/>`;
    s+=`<path id="tr-${rb.id}" fill="none" style="stroke:${c}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`;
    (R.series.offline[rb.id]||[]).forEach(seg=>{s+=`<path d="${seg.map((q,i)=>(i?'L':'M')+X(q[1]).toFixed(1)+','+Y(q[2]).toFixed(1)).join('')}" fill="none" style="stroke:var(--warn)" stroke-width="5" opacity=".45" stroke-linecap="round" data-tip="${esc(`<b>${rb.name}</b>: VICON trail while disconnected<br>${fmtT(seg[0][0])} → ${fmtT(seg[seg.length-1][0])}`)}"/>`;});
    (R.series.robot[rb.id]||[]).forEach(seg=>{s+=`<path d="${seg.map((q,i)=>(i?'L':'M')+X(q[1]).toFixed(1)+','+Y(q[2]).toFixed(1)).join('')}" fill="none" style="stroke:var(--ink)" stroke-width="1.5" stroke-dasharray="4 3" data-tip="${esc(`<b>${rb.name}</b>: robot's own pose log while disconnected`)}"/>`;});
    s+=`<circle cx="${X(p[0][1])}" cy="${Y(p[0][2])}" r="4" fill="var(--surface)" style="stroke:${c}" stroke-width="2"><title>${esc(rb.name)} start</title></circle>`;
    s+=`<g id="rb-${rb.id}"><circle r="7" style="fill:${c};stroke:var(--surface)" stroke-width="2"/><text class="lab" x="11" y="-9" style="font-weight:600"></text></g>`;});
  s+='</svg>';host.innerHTML=s;
  const upd=t=>{R.robots.forEach(rb=>{const p=R.series.path[rb.id];if(!p)return;let i=0;while(i+1<p.length&&p[i+1][0]<=t)i++;const q=p[i];
    const g=host.querySelector('#rb-'+CSS.escape(rb.id)),stale=t>p[p.length-1][0]+1;
    g.setAttribute('transform',`translate(${X(q[1])},${Y(q[2])})`);g.querySelector('text').textContent=rb.name+(stale?' (last known)':'');
    g.querySelector('circle').setAttribute('opacity',stale?.45:1);
    host.querySelector('#tr-'+CSS.escape(rb.id)).setAttribute('d',p.slice(0,i+1).map((r,j)=>(j?'L':'M')+X(r[1]).toFixed(1)+','+Y(r[2]).toFixed(1)).join(''));});};
  cur.subs.push(upd);upd(cur.t);
}

function rateStrip(host,R){
  const ids=Object.keys(R.series.rate);if(!ids.length){host.innerHTML='<div class="note">No telemetry.</div>';return;}
  const W=Math.max(320,host.clientWidth),L=78,rh=30,H=ids.length*rh+22,xmax=Math.max(R.duration,1),iw=W-L-10,x=t=>L+t/xmax*iw;
  let s=`<svg width="${W}" height="${H}" role="img" aria-label="Telemetry samples per second">`;
  ids.forEach((id,i)=>{const rb=R.robots.find(r=>r.id===id),cnt=R.series.rate[id],y0=i*rh,med=[...cnt].filter(v=>v>0).sort((a,b)=>a-b)[Math.floor(cnt.filter(v=>v>0).length/2)]||1,cw=iw/cnt.length;
    s+=`<text class="lab" x="${L-8}" y="${y0+rh/2+4}" text-anchor="end">${esc(rb.name)}</text>`;
    cnt.forEach((v,sec)=>{if(sec>xmax)return;const none=v===0;s+=`<rect x="${x(sec)}" y="${y0+4}" width="${Math.max(1,cw-1)}" height="${rh-8}" ${none?'class="hatch"':`style="fill:var(--s${rb.slot+1})" opacity="${(.25+.75*Math.min(1,v/med)).toFixed(2)}"`} data-tip="${esc(`<b>${rb.name}</b> at ${fmtT(sec)}<br>${v} samples${none?' - nothing received':''}`)}"/>`;});});
  xTicks(xmax).forEach(t=>{s+=`<text x="${x(t)}" y="${H-6}" text-anchor="middle">${fmtT(t)}</text>`;});
  s+=`<line class="cur" y1="0" y2="${ids.length*rh}" x1="0" x2="0"/></svg>`;host.innerHTML=s;
  const line=host.querySelector('.cur'),upd=t=>{line.setAttribute('x1',x(t));line.setAttribute('x2',x(t));};cur.subs.push(upd);upd(cur.t);
}

function stepBands(R){return R.steps.filter(s=>s.start!=null).map(s=>({t0:s.start,t1:s.end==null?R.duration:s.end,label:`Step ${s.n}: ${s.name}`}));}

function renderRun(R){
  cur.subs=[];cur.t=0;
  const lvl=R.verdict.level,botNames=R.robots.map(r=>r.name).join(', ');
  let h=`<section><div class="card verdict"><div><span class="chip ${lvl}">${ICON[lvl]||''} ${esc(R.verdict.chip)}</span> <span class="sub">&nbsp;${esc(fmtClock(R.started))} · ${esc(R.mission)} · ${esc(botNames)}</span></div>
   <div class="hl">${esc(R.verdict.headline)}</div>
   <div class="tiles">${R.tiles.map(t=>`<div class="tile"><div class="l">${esc(t.label)}</div><div class="v ${t.level||''}">${esc(t.value)}</div><div class="s" title="${esc(t.sub)}">${esc(t.sub)}</div></div>`).join('')}</div></div></section>`;
  h+=`<section><h2>What the logs are telling us</h2><div class="card">${R.findings.length?R.findings.map(f=>`<div class="finding"><div class="ic ${f.sev}">${ICON[f.sev]}</div><div><h3>${esc(f.title)}</h3><p>${esc(f.body)}</p>${f.action?`<div class="act"><b>Suggestion:</b> ${esc(f.action)}</div>`:''}</div></div>`).join(''):'<div class="note">Nothing notable.</div>'}</div></section>`;
  if(R.offline.length){h+=`<section><h2>Link dropouts and onboard execution</h2><div class="card scroll"><table><thead><tr><th>Robot</th><th>Henosync lost link</th><th>Restored</th><th>Down for</th><th>Cause</th><th>VICON moved</th><th>Robot log: samples / commanding</th><th>Robot tracked</th><th>Waypoints offline</th><th>Robot saw link down</th><th>Log received</th></tr></thead><tbody>${R.offline.map(w=>`<tr><td>${esc(w.node)}</td><td>${fmtT(w.start)}</td><td>${w.restored?fmtT(w.end):'<span class="bad">never</span>'}</td><td>${fmtDur(w.dur)}</td><td>${w.simulated?'operator (simulated)':'link fault'}</td><td>${(w.vicon_m||0).toFixed(2)} m</td><td>${w.robot_log?`${w.samples} / ${w.cmd_samples}`:'-'}</td><td>${w.robot_log?(w.robot_m||0).toFixed(2)+' m':'-'}</td><td>${w.robot_log?(w.wps.length?w.wps.map(i=>i+1).join(', '):'none'):'-'}</td><td>${w.robot_down?fmtT(w.robot_down[0])+' → '+fmtT(w.robot_down[1]):'-'}</td><td class="${w.robot_log&&w.synced==null?'bad':''}">${w.synced!=null?fmtT(w.synced):(w.robot_log?'not received':'-')}</td></tr>`).join('')}</tbody></table><p class="sub" style="margin:10px 2px 0">"VICON moved" is from Henosync's own VICON connection, which doesn't go through the robot link. The robot columns come from robot.jsonl, which the robot's onboard controller logged itself and delivered after reconnecting. On the map, the thick orange trail is the VICON trail while disconnected; the dashed line is the robot's own pose log for the same window.</p></div></section>`;}
  h+=`<section><h2>What happened, in order</h2><div class="card"><ul class="story">${R.narrative.map(n=>`<li class="${n.sev}"><span class="t">${fmtT(n.t)}</span><span class="dot ${n.sev}"></span><span>${esc(n.text)}</span></li>`).join('')}</ul></div></section>`;
  h+=`<section><h2>Visual replay</h2><div class="scrub"><div class="row"><span class="tt" id="tt">0:00</span><input id="slider" type="range" min="0" max="${R.duration}" step="0.1" value="0" aria-label="Replay time"></div><div class="rd" id="rd"></div></div>
   <div class="card chart"><h3>${esc(R.captions.gantt)}</h3><div class="legend"><span><span class="sw" style="background:var(--s1)"></span>step</span><span><span class="sw" style="background:var(--ok)"></span>robot online</span><span><span class="sw" style="background:var(--warn)"></span>degraded</span><span><span class="sw" style="background:var(--bad)"></span>no data</span><span><span class="sw" style="background:var(--warn);transform:rotate(45deg)"></span>alert</span></div><div id="c-gantt"></div></div>`;
  h+=`<div class="two map"><div class="card chart"><h3>${esc(R.captions.map)}</h3><div id="c-map"></div></div><div class="card chart"><h3>${esc(R.captions.rate)}</h3><div id="c-rate"></div></div></div><div style="height:14px"></div>`;
  const rids=R.robots.filter(r=>R.series.speed[r.id]);
  if(rids.length){h+=`<div class="card chart"><h3>${esc(R.captions.speed)}</h3>${legend(rids.map(r=>({name:r.name,color:col(r.slot)})))}<div id="c-speed"></div></div>`;}
  if(Object.keys(R.series.dist).length){h+=`<div class="card chart"><h3>${esc(R.captions.dist)}</h3><div id="c-dist"></div></div>`;}
  if(R.series.cmd.length){h+=`<div class="card chart"><h3>${esc(R.captions.cmd)}</h3><div class="legend"><span>Forward/back command (m/s)</span></div><div id="c-lin"></div><div class="legend"><span>Turn command (rad/s, + = left)</span></div><div id="c-ang"></div></div>`;}
  const bids=R.robots.filter(r=>R.series.batt[r.id]);
  if(bids.length){h+=`<div class="card chart"><h3>${esc(R.captions.batt)}</h3>${legend(bids.map(r=>({name:r.name,color:col(r.slot)})))}<div id="c-batt"></div></div>`;}
  h+='</section>';
  h+=`<section><h2>Step by step</h2><div class="card scroll"><table><thead><tr><th>#</th><th>Step</th><th>Robot</th><th>Target</th><th>Started</th><th>Took</th><th>Robot at rest</th><th>Waited after</th><th>Final error</th><th>Outcome</th></tr></thead><tbody>${R.steps.map(s=>`<tr><td>${s.n}</td><td>${esc(s.name)}</td><td>${esc(s.robot||'-')}</td><td>${esc(s.target||'-')}</td><td>${s.start!=null?fmtT(s.start):'-'}</td><td>${fmtDur(s.duration)}</td><td>${s.settle!=null?fmtT(s.settle):'-'}</td><td class="${s.idle_after>10?'warn':''}">${s.idle_after!=null?fmtDur(s.idle_after):'-'}</td><td>${s.err!=null?s.err.toFixed(3)+' m':'-'}</td><td class="${s.outcome==='completed'?'ok':'warn'}">${esc(s.outcome)}</td></tr>`).join('')}</tbody></table></div></section>`;
  h+=`<section><h2>The files behind this run</h2><div class="files">${R.files.map(f=>`<div class="card file"><h3>${esc(f.name)}</h3><div class="m">${(f.size/1024).toFixed(1)} KB · ${f.lines.toLocaleString()} lines</div><p>${esc(f.desc)}</p><p class="learn"><b>In this run:</b> ${esc(f.info)}</p><details><summary>${f.truncated?`Show first ${f.shown_lines} of ${f.lines.toLocaleString()} lines`:'Show contents'}</summary><pre>${esc(f.preview)}</pre></details></div>`).join('')}</div></section>`;
  document.getElementById('main').innerHTML=h;
  drawCharts(R);
  const sl=document.getElementById('slider');
  sl.addEventListener('input',()=>setT(+sl.value));
  bindReadout(R);
}
function bindReadout(R){
  const sl=document.getElementById('slider'),tt=document.getElementById('tt'),rd=document.getElementById('rd');
  const readout=t=>{tt.textContent=fmtT(t);sl.value=t;rd.innerHTML=R.robots.map(r=>{const sp=valueAt(R.series.speed[r.id]||[],t),bt=valueAt(R.series.batt[r.id]||[],t),stale=r.last_t!=null&&t>r.last_t+1;
    const st=(R.status_segs[r.id]||[]).find(g=>t>=g[0]&&t<g[1]);
    return `<span><span class="sw" style="background:${col(r.slot)}"></span><b>${esc(r.name)}</b> ${stale?'<span class="bad">no data</span>':(st?esc(st[2]):'')}${sp?' · '+sp[1].toFixed(2)+' m/s':''}${bt?' · '+bt[1].toFixed(0)+'%':''}</span>`;}).join('');
    const ev=R.narrative.filter(n=>n.t<=t).pop();if(ev)rd.innerHTML+=`<span style="flex-basis:100%">Latest: ${esc(ev.text)}</span>`;};
  cur.subs.push(readout);readout(cur.t);
}
function drawCharts(R){
  cur.subs=cur.subs.slice(0,0);
  const xmax=Math.max(R.duration,1),bands=stepBands(R),$=id=>document.getElementById(id);
  gantt($('c-gantt'),R);mapChart($('c-map'),R);rateStrip($('c-rate'),R);
  if($('c-speed'))lineChart($('c-speed'),{xmax,ymin:0,ymax:Math.max(.3,...R.robots.map(r=>(R.series.speed[r.id]||[]).reduce((m,p)=>Math.max(m,p[1]),0)))*1.1,bands,
    series:R.robots.filter(r=>R.series.speed[r.id]).map(r=>({name:r.name,color:col(r.slot),pts:R.series.speed[r.id]})),yfmt:v=>v.toFixed(1)+'',vfmt:v=>v.toFixed(2)+' m/s',aria:'Speed over time'});
  if($('c-dist')){const mx=Math.max(...Object.values(R.series.dist).flat().filter(p=>p).map(p=>p[1]));
    lineChart($('c-dist'),{xmax,ymin:0,ymax:Math.ceil(mx),bands,series:R.robots.filter(r=>R.series.dist[r.id]).map(r=>({name:r.name+' to target',color:col(r.slot),pts:R.series.dist[r.id]})),yfmt:v=>v+' m',vfmt:v=>v.toFixed(2)+' m',aria:'Distance to target'});}
  if($('c-lin')){const c=R.series.cmd;const lin=c.map(p=>[p[0],p[1]]),ang=c.map(p=>[p[0],p[2]]);const end=R.steps.length&&R.steps[R.steps.length-1].end!=null?R.steps[R.steps.length-1].end:xmax;lin.push([end,c[c.length-1][1]]);ang.push([end,c[c.length-1][2]]);
    lineChart($('c-lin'),{h:120,xmax,ymin:-.6,ymax:.6,series:[{name:'forward/back',color:'var(--s1)',pts:lin,step:true}],yfmt:v=>v.toFixed(1),vfmt:v=>v.toFixed(1)+' m/s'});
    lineChart($('c-ang'),{h:120,xmax,ymin:-.6,ymax:.6,series:[{name:'turn',color:'var(--s2)',pts:ang,step:true}],yfmt:v=>v.toFixed(1),vfmt:v=>v.toFixed(1)+' rad/s'});}
  if($('c-batt')){lineChart($('c-batt'),{xmax,ymin:0,ymax:100,series:R.robots.filter(r=>R.series.batt[r.id]).map(r=>({name:r.name,color:col(r.slot),pts:R.series.batt[r.id]})),yfmt:v=>v+'%',vfmt:v=>v.toFixed(1)+'%',aria:'Battery over time'});}
}
function renderOverview(){
  const rs=D.runs;
  let h=`<section><h2>All runs at a glance</h2><div class="card scroll"><table><thead><tr><th>When</th><th>Mission</th><th>Verdict</th><th>Length</th><th>Robots</th><th>Steps</th><th>Alerts</th></tr></thead><tbody>${rs.map((r,i)=>`<tr class="click" data-i="${i}"><td>${esc(fmtClock(r.started))}</td><td>${esc(r.mission)}</td><td><span class="chip ${r.verdict.level}">${ICON[r.verdict.level]||''} ${esc(r.verdict.chip)}</span></td><td>${fmtDur(r.duration)}</td><td>${esc(r.robots.map(x=>x.name).join(', '))}</td><td>${r.steps.filter(s=>s.outcome==='completed').length}/${r.steps.length}</td><td class="${r.n_faults?'bad':''}">${r.n_faults}</td></tr>`).join('')}</tbody></table></div></section>`;
  h+=`<section><h2>In plain English</h2>${rs.map((r,i)=>`<div class="card" style="margin-bottom:10px"><span class="chip ${r.verdict.level}">${ICON[r.verdict.level]||''} ${esc(r.verdict.chip)}</span> <span class="sub">${esc(fmtClock(r.started))}</span><p style="margin:8px 0 4px;font-weight:600">${esc(r.verdict.headline)}</p><a href="#run${i}" style="font-size:13px">Open full breakdown →</a></div>`).join('')}</section>`;
  if(D.cross.length)h+=`<section><h2>Across runs</h2><div class="card">${D.cross.map(f=>`<div class="finding"><div class="ic ${f.sev}">${ICON[f.sev]}</div><div><h3>${esc(f.title)}</h3><p>${esc(f.body)}</p></div></div>`).join('')}</div></section>`;
  document.getElementById('main').innerHTML=h;
  document.querySelectorAll('tr.click').forEach(tr=>tr.addEventListener('click',()=>{location.hash='run'+tr.dataset.i;}));
}
function route(){
  const m=location.hash.match(/run(\d+)/),i=m?+m[1]:-1;
  document.querySelectorAll('#nav button').forEach(b=>b.setAttribute('aria-current',String(+b.dataset.i===i)));
  hideTip();window.scrollTo(0,0);
  if(i>=0&&D.runs[i])renderRun(D.runs[i]);else renderOverview();
}
document.getElementById('sub').textContent=`${D.runs.length} run${D.runs.length===1?'':'s'} · source: ${D.source} · generated ${new Date(D.generated*1000).toLocaleString()}`;
document.getElementById('nav').innerHTML=`<button data-i="-1">Overview</button>`+D.runs.map((r,i)=>`<button data-i="${i}">${esc(fmtClock(r.started))} · ${esc(r.mission)}</button>`).join('');
document.querySelectorAll('#nav button').forEach(b=>b.addEventListener('click',()=>{location.hash=+b.dataset.i<0?'':'run'+b.dataset.i;if(+b.dataset.i<0&&!location.hash)route();}));
addEventListener('hashchange',route);
let rz;addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(()=>{const m=location.hash.match(/run(\d+)/);if(m&&D.runs[+m[1]]){const R=D.runs[+m[1]];drawCharts(R);bindReadout(R);}},200);});
route();
</script></body></html>
"""

if __name__ == "__main__":
    main()
