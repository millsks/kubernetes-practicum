# m01-lab1 · Write a ReplicaSet controller

Every Kubernetes controller is a reconcile loop. Write the decision logic of a ReplicaSet controller in plain Python,
then drive it to a fixed point.

```sh
pixi run start m01-lab1
# edit work/m01-lab1/reconciler.py
pixi run grade m01-lab1
```

`reconciler.py` documents the Pod shape. `apply_actions` and `settle` are provided and stand in for the API server,
the scheduler, and the kubelet. Use only the standard library.

## Specification

### `active(pods)`

Return the Pods that count toward the replica total: phase `Pending` or `Running`, and not `deleting`. Keep the
input order.

### `reconcile(desired, pods, prefix="web")`

Return `{"create": [...], "delete": [...]}` with both lists **sorted**.

| Rule | Why |
| --- | --- |
| `desired < 0` raises `ValueError` | |
| Too few active Pods: create exactly the missing number | The real controller creates `desired - active` |
| New names are `f"{prefix}-{n}"` using the smallest positive integers `n` not used by **any** existing Pod name (terminating and failed ones included) | Names must be unique while the old Pod still exists |
| Too many active Pods: delete exactly the surplus, choosing (1) unscheduled Pods (`node` is `None`) first, then (2) not-ready Pods, then (3) the newest (`created` highest); break ties by name | Remove the Pods least likely to be serving traffic, as Kubernetes does |
| Every `Failed` Pod that isn't already `deleting` is also deleted (cleanup), whatever the count | Failed Pods don't count, and shouldn't linger |
| Never delete a Pod that is already `deleting` | Deleting twice is a wasted API call, and a common bug |
| Nothing to do returns `{"create": [], "delete": []}` | Idempotence |

### `converge(desired, pods, prefix="web", max_rounds=10)`

Loop: `actions = reconcile(...)`; if both lists are empty, stop; otherwise `pods = settle(apply_actions(pods,
actions))` and count one round. Return `(pods, rounds)`. If it hasn't stopped after `max_rounds` rounds, raise
`RuntimeError`. Calling `converge` again on its own result must return 0 rounds.

## Done when

`pixi run grade m01-lab1` passes.
