# m02-lab2 · Pod triage

Write `triage.py`, a small command-line tool that reads `kubectl get pods -o json` and tells you, for every unhealthy
Pod, what's wrong and what to run next. Use **only the standard library**: no kubelab, no PyYAML. On a locked-down
machine you may have nothing but Python and kubectl.

```sh
pixi run start m02-lab2
# edit work/m02-lab2/triage.py
pixi run grade m02-lab2
kubectl get pods -A -o json | pixi run python work/m02-lab2/triage.py
```

## Input

JSON from `kubectl get pods [-A] -o json`: an object with an `items` list. Read it from the file named by the first
argument, or from standard input when there is no argument.

## `diagnose(pod)`

Return `(reason, container)` or `None`. Check in this order; the first match wins:

| # | Condition | reason | container |
| --- | --- | --- | --- |
| 1 | `status.phase` is `Succeeded` | return `None` (completed is healthy) | |
| 2 | a condition `PodScheduled` has status `False` | `Unschedulable` | `""` |
| 3 | for each container status (init containers first, then containers), in order: |  |  |
| 3a | `lastState.terminated.reason` or `state.terminated.reason` is `OOMKilled` | `OOMKilled` | its name |
| 3b | `state.waiting.reason` is one of `ErrImagePull`, `ImagePullBackOff`, `CreateContainerConfigError`, `CreateContainerError`, `CrashLoopBackOff` | that reason | its name |
| 3c | `state.terminated.exitCode` is non-zero | `Error` | its name |
| 4 | `status.phase` is `Running` and some container status has `ready: false` | `NotReady` | the first such container |
| 5 | otherwise | `None` | |

## `next_command(pod, reason, container)`

Use the Pod's namespace (`default` if missing) and name:

| reason | command |
| --- | --- |
| `OOMKilled`, `CrashLoopBackOff`, `Error` | `kubectl logs -n NS NAME -c CONTAINER --previous` |
| everything else | `kubectl describe pod -n NS NAME` |

## Output and exit code

One line per unhealthy Pod, in input order, fields separated by **tabs**: `NS/NAME`, `REASON`, `COMMAND`. Print
nothing for healthy and completed Pods. Exit `0` when every Pod is healthy, `1` when any is unhealthy, and `2` with a
message on standard error when the input isn't valid JSON with an `items` list.

## Done when

`pixi run grade m02-lab2` passes, and you've run it against your own cluster.
