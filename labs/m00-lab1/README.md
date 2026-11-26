# m00-lab1 · The primer cluster

Write the kind configuration you'll use for the whole course, answer a few questions about the two container
runtimes, then create the cluster.

```sh
pixi run start m00-lab1
# edit work/m00-lab1/kind-primer.yaml and work/m00-lab1/answers.toml
pixi run grade m00-lab1
kind create cluster --config work/m00-lab1/kind-primer.yaml
pixi run grade-live m00-lab1      # optional: checks the running cluster
```

## Specification: `kind-primer.yaml`

| Requirement | Why |
| --- | --- |
| `kubelab.check_kind_config` reports no problems | kind rejects malformed configs, sometimes only after creating half a cluster |
| `name: primer` | Every lab and the live checks use the `kind-primer` context |
| Exactly one `control-plane` node and two `worker` nodes, in that order | Scheduling, spreading, and draining need more than one node |
| The control-plane node maps `containerPort: 30080` to `hostPort: 8080` over TCP | Stage 2's gateway listens on NodePort 30080; you'll reach it at `localhost:8080` |
| No other host ports | Keep your Mac's ports free |
| No `TODO` left in the file | |

## Specification: `answers.toml`

| Key | Expected |
| --- | --- |
| `pod_runtime` | The runtime the kubelet drives over CRI inside each node |
| `node_engine` | What creates kind's node containers in this setup (one word) |
| `load_command` | A `kind load docker-image ...` command for `app:0.1.0` that targets the `primer` cluster |
| `inspect_cli` | The CRI debugging CLI available inside each node |
| `colima_cpus`, `colima_memory_gb` | What you started Colima with: at least 4 CPUs and 6 GB |

## Live checks (optional)

`pixi run grade-live m00-lab1` asks the `kind-primer` context for its nodes and checks that there are three, all
`Ready`, one control plane and two workers, each reporting a `containerd://` runtime.

## Done when

`pixi run grade m00-lab1` passes and `kubectl get nodes` shows three Ready nodes.
