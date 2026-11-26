/* Kubernetes visualizers: the reconcile loop of a ReplicaSet, and a Deployment's rolling update step by step. */
(() => {
  "use strict";
  const { registerViz } = window.PPViz;

  /* ---------------- reconcile: desired vs actual, one controller step at a time ---------------- */
  const NODES = ["worker", "worker2"];
  const RECONCILE = [
    { event: "You apply a ReplicaSet with replicas: 3.", desired: 3, change: (p) => p, act: "create" },
    { event: "Nothing changed: actual matches desired, so the controller does nothing.", desired: 3, change: (p) => p, act: "none" },
    { event: "Someone runs kubectl delete pod on one replica.", desired: 3, change: (p) => p.slice(1), act: "create" },
    { event: "You scale up: kubectl scale rs/web --replicas=5.", desired: 5, change: (p) => p, act: "create" },
    { event: "Node 'worker2' dies. Its Pods are gone.", desired: 5, change: (p) => p.filter((x) => x.node !== "worker2"), act: "create", lost: "worker2" },
    { event: "You scale down to 2. The controller deletes the surplus.", desired: 2, change: (p) => p, act: "delete" },
  ];

  registerViz("reconcile", (el, config, api) => {
    const { h, s } = api;
    const ui = api.shell(el, { title: "A ReplicaSet keeps actual = desired", kind: "Reconcile loop" });
    const svg = s("svg", { viewBox: "0 0 640 250", width: "100%", role: "img", "aria-label": "Reconcile loop", style: "max-width:640px;height:auto;font-family:var(--font-sans)" });
    ui.stage.append(svg);
    ui.setLegend([["ready Pod", "var(--accent)"], ["new Pod (just created)", "var(--viz-2)"], ["being deleted", "var(--bad)"]]);

    function frames() {
      const out = [];
      let pods = [];
      let next = 1;
      let lost = null;
      for (const step of RECONCILE) {
        pods = step.change(pods.map((p) => ({ ...p, fresh: false })));
        lost = step.lost || lost;
        const observe = pods.length;
        out.push({ phase: "observe", step, pods: pods.map((p) => ({ ...p })), observe, lost, say: `${step.event} Observe: desired ${step.desired}, actual ${observe}.` });
        const diff = step.desired - pods.length;
        if (diff > 0) {
          const live = NODES.filter((n) => n !== lost);
          for (let i = 0; i < diff; i++) {
            const load = (n) => pods.filter((p) => p.node === n).length;
            const node = live.reduce((best, n) => (load(n) < load(best) ? n : best), live[0]);
            pods.push({ id: `web-${String(next++).padStart(2, "0")}`, node, fresh: true });
          }
          out.push({ phase: "act", step, pods: pods.map((p) => ({ ...p })), observe, lost, say: `Diff = ${diff}. Act: create ${diff} Pod${diff > 1 ? "s" : ""}; the scheduler places ${diff > 1 ? "them" : "it"} on a healthy node.` });
        } else if (diff < 0) {
          const marked = pods.map((p, i) => ({ ...p, dying: i >= step.desired }));
          out.push({ phase: "act", step, pods: marked, observe, lost, say: `Diff = ${diff}. Act: delete ${-diff} Pod${diff < -1 ? "s" : ""}.` });
          pods = pods.slice(0, step.desired);
        } else {
          out.push({ phase: "act", step, pods: pods.map((p) => ({ ...p })), observe, lost, say: "Diff = 0. Act: nothing. A controller that has nothing to do does nothing." });
        }
      }
      return out;
    }

    function render(frame) {
      svg.replaceChildren();
      const box = (x, y, w, hgt, label, sub, active) => [
        s("rect", { x, y, width: w, height: hgt, rx: 8, fill: active ? "var(--accent-soft)" : "var(--bg-elev)", stroke: active ? "var(--accent)" : "var(--border-strong)", "stroke-width": active ? 2.2 : 1.2 }),
        s("text", { x: x + w / 2, y: y + 22, "text-anchor": "middle", "font-size": 13, "font-weight": 600, fill: "var(--fg)", text: label }),
        s("text", { x: x + w / 2, y: y + 40, "text-anchor": "middle", "font-size": 11, fill: "var(--fg-muted)", text: sub }),
      ];
      svg.append(...box(10, 10, 170, 56, `desired: ${frame.step.desired}`, "spec.replicas", false));
      svg.append(...box(10, 86, 170, 56, "controller", frame.phase === "observe" ? "observe → diff" : "act", true));
      svg.append(...box(10, 162, 170, 56, `actual: ${frame.pods.filter((p) => !p.dying).length}`, "Pods that exist", false));
      NODES.forEach((n, i) => {
        const x = 210 + i * 215;
        const dead = frame.lost === n;
        svg.append(
          s("rect", { x, y: 10, width: 200, height: 230, rx: 10, fill: "none", stroke: dead ? "var(--bad)" : "var(--border-strong)", "stroke-dasharray": dead ? "6 4" : null }),
          s("text", { x: x + 12, y: 30, "font-size": 12, "font-weight": 600, fill: dead ? "var(--bad)" : "var(--fg-muted)", text: dead ? `${n} (NotReady)` : n }),
        );
        frame.pods.filter((p) => p.node === n).forEach((p, j) => {
          const px = x + 12 + (j % 2) * 92;
          const py = 44 + Math.floor(j / 2) * 46;
          const fill = p.dying ? "var(--bad)" : p.fresh ? "var(--viz-2)" : "var(--accent)";
          svg.append(
            s("rect", { x: px, y: py, width: 84, height: 36, rx: 6, fill, opacity: p.dying ? 0.55 : 1 }),
            s("text", { x: px + 42, y: py + 23, "text-anchor": "middle", "font-size": 12, "font-weight": 600, fill: "var(--accent-fg)", text: p.id }),
          );
        });
      });
      ui.setLog(api.esc(frame.say));
    }
    const play = api.player(ui.controls, render, { speed: 1200 });
    play.load(frames());
  });

  /* ---------------- rollout: a Deployment moving from v1 to v2 ---------------- */
  function resolve(value, replicas, up) {
    const t = String(value).trim();
    if (t.endsWith("%")) { const exact = (replicas * parseFloat(t)) / 100; return up ? Math.ceil(exact) : Math.floor(exact); }
    return Math.max(0, parseInt(t, 10) || 0);
  }

  function rolloutFrames(replicas, surgeIn, unavailIn) {
    const surge = resolve(surgeIn, replicas, true);
    const unavail = resolve(unavailIn, replicas, false);
    if (surge === 0 && unavail === 0) return { error: "maxSurge and maxUnavailable can't both be 0: the rollout could never start." };
    const maxTotal = replicas + surge;
    const minReady = Math.max(0, replicas - unavail);
    let oldPods = replicas;
    let newReady = 0;
    let newStarting = 0;
    const frames = [{ oldPods, newReady, newStarting, maxTotal, minReady, say: `Start: ${replicas} × v1 ready. Limits: at most ${maxTotal} Pods, at least ${minReady} ready.` }];
    let guard = 0;
    while ((oldPods > 0 || newStarting > 0 || newReady < replicas) && guard++ < 60) {
      const ready = oldPods + newReady;
      const canKill = Math.min(oldPods, Math.max(0, ready - minReady));
      const total = oldPods + newReady + newStarting - canKill;
      const canStart = Math.max(0, Math.min(maxTotal - total, replicas - newReady - newStarting));
      oldPods -= canKill;
      newStarting += canStart;
      frames.push({ oldPods, newReady, newStarting, killed: canKill, maxTotal, minReady,
        say: `Scale v1 down by ${canKill} and v2 up by ${canStart}. Ready now: ${oldPods + newReady} (never below ${minReady}); total ${oldPods + newReady + newStarting} (never above ${maxTotal}).` });
      if (newStarting) {
        newReady += newStarting;
        frames.push({ oldPods, newReady, newStarting: 0, maxTotal, minReady, say: `${newStarting} v2 Pod${newStarting > 1 ? "s" : ""} pass the readiness probe and start taking traffic.` });
        newStarting = 0;
      }
    }
    frames.push({ oldPods: 0, newReady: replicas, newStarting: 0, maxTotal, minReady, say: `Done: ${replicas} × v2. The old ReplicaSet stays at 0 replicas so you can roll back.` });
    return { frames };
  }

  registerViz("rollout", (el, config, api) => {
    const { h } = api;
    const ui = api.shell(el, { title: "Rolling update from v1 to v2", kind: "Rollout" });
    const rep = h("input", { type: "number", min: 1, max: 12, value: config.replicas ?? 4, style: "width:4.5em" });
    const sur = h("input", { type: "text", value: String(config.maxSurge ?? 1), style: "width:4.5em" });
    const una = h("input", { type: "text", value: String(config.maxUnavailable ?? 0), style: "width:4.5em" });
    const grid = h("div", { style: "display:flex;flex-direction:column;gap:10px" });
    ui.stage.append(grid);
    ui.setLegend([["v1 ready", "var(--fg-muted)"], ["v2 starting", "var(--viz-2)"], ["v2 ready", "var(--accent)"], ["v1 terminating", "var(--bad)"]]);
    const pod = (label, bg, fg, extra = "") => h("span", { style: `display:inline-grid;place-items:center;width:54px;height:36px;border-radius:6px;font:600 0.75rem var(--font-mono);background:${bg};color:${fg};${extra}`, text: label });
    function render(f) {
      const row = (title, pods) => h("div", {}, h("div", { style: "font-size:0.75rem;color:var(--fg-muted);margin-bottom:4px", text: title }), h("div", { style: "display:flex;gap:6px;flex-wrap:wrap;min-height:36px" }, pods));
      const old = [...Array(f.oldPods)].map(() => pod("v1", "var(--bg-sunk)", "var(--fg)", "border:1.5px solid var(--fg-muted)"));
      const killed = [...Array(f.killed || 0)].map(() => pod("v1 ✕", "var(--bad-soft)", "var(--bad)", "border:1.5px dashed var(--bad)"));
      const ready = [...Array(f.newReady)].map(() => pod("v2", "var(--accent)", "var(--accent-fg)"));
      const starting = [...Array(f.newStarting)].map(() => pod("v2…", "var(--bg-elev)", "var(--fg)", "border:1.5px dashed var(--viz-2)"));
      grid.replaceChildren(row("old ReplicaSet (v1)", [...old, ...killed]), row("new ReplicaSet (v2)", [...ready, ...starting]));
      ui.setLog(api.esc(f.say));
    }
    const play = api.player(ui.controls, render, { speed: 900 });
    const reload = () => {
      const result = rolloutFrames(Math.max(1, Math.min(12, Number(rep.value) || 1)), sur.value, una.value);
      if (result.error) { play.load([{ oldPods: 0, newReady: 0, newStarting: 0, say: result.error }]); return; }
      play.load(result.frames);
    };
    [rep, sur, una].forEach((i) => i.addEventListener("change", reload));
    ui.controls.prepend(api.label("replicas", rep), api.label("maxSurge", sur), api.label("maxUnavailable", una));
    reload();
  });
})();
