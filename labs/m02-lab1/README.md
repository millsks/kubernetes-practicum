# m02-lab1 · A production-shaped Pod

Write `pod.yaml` for [podinfo](https://github.com/stefanprodan/podinfo) the way you'd ship it: health probes,
resources, and the `restricted` security settings. In M03 you'll wrap this same Pod spec in a Deployment.

```sh
pixi run start m02-lab1
# edit work/m02-lab1/pod.yaml
pixi run grade m02-lab1
pixi run grade-live m02-lab1      # optional: applies it to the primer cluster and waits for Ready
```

## Specification

| Requirement | Why |
| --- | --- |
| Exactly one object: a `Pod` named `podinfo` with label `app.kubernetes.io/name: podinfo` | Labels are how everything else will find it |
| `kubelab.check_object` reports no problems | The API server would reject it otherwise |
| `kubelab.warnings` reports nothing except the "bare Pod" warning | You'll fix that one in M03 with a Deployment |
| One container, `app`, image `ghcr.io/stefanprodan/podinfo:6.7.1` | A pinned tag makes the result repeatable |
| `containerPort: 9898` named `http` | Probes refer to it by name |
| `startupProbe` and `livenessProbe` use `httpGet` on `/healthz`; `readinessProbe` uses `httpGet` on `/readyz`; all three on port `http` | podinfo's health endpoints |
| The startup probe allows at least 30 seconds (`failureThreshold × periodSeconds ≥ 30`) | Protects a slow first boot |
| QoS class `Burstable`: CPU request at most `100m`, memory request at least `32Mi`, memory limit at least the request and at most `256Mi`, no CPU limit | Modest requests, a ceiling on memory, no throttling |
| Pod `securityContext.runAsUser` is a non-zero integer, and the container has `readOnlyRootFilesystem: true` | podinfo's image declares a named user; restricted needs a numeric one |

## Live check (optional)

`pixi run grade-live m02-lab1` creates a throwaway namespace on the primer cluster, applies your Pod, waits up to two
minutes for it to become `Ready`, confirms the reported QoS class, and deletes the namespace.

## Done when

`pixi run grade m02-lab1` passes (and, if you ran it, the live check too).
