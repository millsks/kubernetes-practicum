/* Curriculum manifest. The object below must stay valid JSON: practicum check-site parses it. */
window.CURRICULUM = {
  "title": "Kubernetes Practicum",
  "python": "3.14",
  "badge": "kind on your Mac",
  "parts": [
    {
      "id": "part0",
      "number": 0,
      "title": "Orientation",
      "level": "Start here",
      "summary": "Install the toolchain, start Colima, create a three-node kind cluster, and see where Docker ends and containerd begins.",
      "modules": [
        {
          "id": "m00",
          "title": "Your Mac Lab: Colima and kind",
          "href": "modules/m00-mac-lab.html",
          "minutes": 90,
          "summary": "How this practicum works, the toolchain, Colima and kind, Docker vs containerd, the primer cluster, and keeping it healthy."
        }
      ],
      "projects": []
    },
    {
      "id": "part1",
      "number": 1,
      "title": "Stage 1 · Foundations",
      "level": "Level 1 · Novice",
      "summary": "How Kubernetes thinks, the Pod, and the controllers that keep Pods running: Deployments, rollouts, and the other workload kinds.",
      "modules": [
        {
          "id": "m01",
          "title": "How Kubernetes Thinks",
          "href": "modules/m01-how-kubernetes-thinks.html",
          "minutes": 120,
          "summary": "The control plane and nodes, the API and its objects, desired vs actual state, controllers and reconciliation, and the kubectl verbs you use daily."
        },
        {
          "id": "m02",
          "title": "Pods",
          "href": "modules/m02-pods.html",
          "minutes": 150,
          "summary": "Pod anatomy, the lifecycle, probes, requests and limits and QoS, init containers and native sidecars, security context, and debugging a Pod."
        },
        {
          "id": "m03",
          "title": "Deployments and Workloads",
          "href": "modules/m03-deployments-and-workloads.html",
          "minutes": 150,
          "summary": "ReplicaSets and Deployments, label selectors, rolling updates and rollbacks, maxSurge and maxUnavailable, and when to use a StatefulSet, DaemonSet, Job, or CronJob."
        }
      ],
      "projects": []
    }
  ],
  "reference": [
    {
      "id": "ref-roadmap",
      "title": "Roadmap",
      "href": "reference/roadmap.html",
      "summary": "Stages 2-4 (networking, packaging and scaling, production) and the GitOps capstone."
    },
    {
      "id": "ref-kubelab",
      "title": "kubelab Reference",
      "href": "reference/kubelab.html",
      "summary": "Every kubelab helper used in lessons and lab checks: manifests, quantities, selectors, validation, workloads, kind configs, and lint."
    },
    {
      "id": "ref-cheatsheet",
      "title": "kubectl and kind Cheat Sheet",
      "href": "reference/cheatsheet.html",
      "summary": "The commands, fields, and Pod states from Stage 1 on one page."
    },
    {
      "id": "ref-glossary",
      "title": "Glossary",
      "href": "reference/glossary.html",
      "summary": "Terms used in the course, with links to where each is taught."
    }
  ]
};
