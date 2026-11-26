# m03-lab1 · A zero-downtime release

Wrap your podinfo Pod in a Deployment that can never drop below four ready Pods during a rollout, add a CronJob that
never overlaps itself, and show you can predict how both behave.

```sh
pixi run start m03-lab1
# edit work/m03-lab1/deployment.yaml, cronjob.yaml, rollout.toml
pixi run grade m03-lab1
pixi run grade-live m03-lab1      # optional: a real rollout and rollback on the primer cluster
```

## Specification: `deployment.yaml`

| Requirement | Why |
| --- | --- |
| One `Deployment` named `podinfo`; selector and template labels use `app.kubernetes.io/name: podinfo` | Recommended labels; the selector can never change later |
| `kubelab.check_object` reports no problems and `kubelab.warnings` reports **nothing** | Everything from M02, now in a controller |
| `replicas: 4`, `strategy.type: RollingUpdate`, `maxSurge: 1`, `maxUnavailable: 0` (integers) | Never fewer than four ready Pods |
| `minReadySeconds` between 5 and 30 | A new Pod must prove itself before it counts |
| `progressDeadlineSeconds` between 60 and 600 | A stuck rollout is reported, not ignored |
| `revisionHistoryLimit` between 3 and 10 | Enough history to roll back, not unbounded |
| A non-empty `kubernetes.io/change-cause` annotation on the Deployment | Shows in `kubectl rollout history` |
| Image `ghcr.io/stefanprodan/podinfo:6.7.0` and a readiness probe on the named port `http` | The live check rolls to 6.7.1 and back |

## Specification: `cronjob.yaml`

| Requirement | Why |
| --- | --- |
| One `CronJob` named `podinfo-report`; `kubelab.check_object` reports no problems | |
| `timeZone` set | Otherwise the schedule is in the controller's time zone |
| `concurrencyPolicy: Forbid` and `startingDeadlineSeconds` set | No overlapping runs; no surprise catch-up runs |
| `successfulJobsHistoryLimit` at most 3, `failedJobsHistoryLimit` at least 1 | Keep evidence of failures without clutter |
| Job `backoffLimit` at most 3 and `activeDeadlineSeconds` set | Bounded retries and run time |
| Container image pinned (not `:latest`), with CPU and memory requests and a memory limit | Same hygiene as long-running Pods |

## Specification: `rollout.toml`

Answer every key from your own `deployment.yaml` and the lesson. `max_pods` and `min_ready` must match
`kubelab.rollout_bounds` for your settings.

## Live check (optional)

In a throwaway namespace: apply both files, wait for the rollout, `set image` to 6.7.1 and wait, `rollout undo` and
wait, then check that the live image is 6.7.0 again and that the history has three revisions. It also triggers one run
of the CronJob and waits for the Job to complete.

**Stretch:** while the live check runs, watch from another terminal:

```sh
kubectl -n <namespace> get rs,pods -w
```

## Done when

`pixi run grade m03-lab1` passes.
