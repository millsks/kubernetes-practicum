# kubernetes-practicum

An interactive Kubernetes course from your first Pod to a platform deployed entirely from Git, all on your Mac with
kind and Colima: Pods, Deployments, Services, Gateway API, Helm, autoscaling, security, observability, and Argo CD,
with graded labs and a multi-tier capstone.

You write every manifest and tool yourself. The course explains the ideas, drills them with exercises in the browser,
and checks your work in labs. It never hands you the answers.

[![CI](https://github.com/millsks/kubernetes-practicum/actions/workflows/ci.yml/badge.svg)](https://github.com/millsks/kubernetes-practicum/actions/workflows/ci.yml)
![pixi](https://img.shields.io/badge/managed%20by-pixi-orange)

## What's inside

- **Stage 1 · Foundations:** an orientation module (your Mac lab: Colima, kind, Docker vs containerd) and three
  modules: how Kubernetes thinks, Pods, and Deployments and workloads. Each has runnable cells, graded exercises, a
  quiz, flashcards, and labs. Published as static HTML in [`docs/`](docs/).
- **Stages 2–4 and the capstone** (networking, Helm, autoscaling, security, observability, GitOps with Argo CD, and a
  GitOps-run notes platform) are next on the [roadmap](docs/reference/roadmap.html).
- **kubelab** ([`src/kubelab/`](src/kubelab/)): a small library that loads manifests, parses resource quantities,
  matches label selectors, validates objects the way the API server would, flags best-practice gaps, checks kind
  configs, and diagnoses unhappy Pods. It runs in the browser (Pyodide) for exercises and locally for lab checks. It
  never talks to a cluster.
- **Labs** ([`labs/`](labs/)): a README specification, a starter workspace, and checks. **Labs ship without
  solutions**; CI proves every untouched starter fails its checks, so a passing grade means you built it. Offline
  checks need no cluster; optional live checks apply your work to the `primer` kind cluster.

## Installation

On macOS, install the VM and cluster tools with [Homebrew](https://brew.sh), then [Pixi](https://pixi.sh):

```sh
brew install colima docker kind
colima start --cpu 4 --memory 8 --disk 60 --vm-type vz --mount-type virtiofs

git clone https://github.com/millsks/kubernetes-practicum.git
cd kubernetes-practicum
pixi install            # Python, kubelab, kubectl, and helm
pixi run bootstrap      # pre-commit hooks (only needed if you contribute)
```

On an Intel Mac, also run `brew install kubectl` (conda-forge has no current kubectl build for osx-64).

## Quick start

```sh
pixi run serve              # opens the course at http://127.0.0.1:8000/
```

Start with **Module 00: Your Mac Lab**. Each module ends with labs:

```sh
pixi run labs               # list labs and whether you've started them
pixi run start m02-lab1     # copy the starter into work/m02-lab1/
# read labs/m02-lab1/README.md and do the work in work/m02-lab1/
pixi run grade m02-lab1     # run the lab's checks against a copy of your work
pixi run grade-live m02-lab1  # optional: also apply it to the primer cluster
```

Grading copies your workspace to `build/labs/<lab>/`, so checks never modify `work/`. Live checks use the
`kind-primer` context (override with `PRACTICUM_CONTEXT`) and create throwaway namespaces that they delete afterwards.

## Single-file edition

`pixi run bundle` writes `dist/kubernetes-practicum.html`: every page in one file, for the
[practicums](https://github.com/millsks/practicums) collection.

## Contributing

`pixi run ci` runs everything CI runs: pre-commit, build, mypy, ruff, the site and exercise checks, the lab checks,
and the tests with a 90% coverage gate. Authoring conventions are in [`docs/AUTHORING.md`](docs/AUTHORING.md).

## License

MIT
