# ADR-005: Ingress on EKS with the AWS Load Balancer Controller

- Status: Accepted
- Date: 2026-10-14

## Context

The EKS environments need public HTTPS for the web app and API, and a way to
issue certificates. The original Phase 12 plan named "an ingress
controller", and the chart's network policy already expected ingress-nginx.
Three facts shape the choice:

- The Kubernetes project retired **ingress-nginx** in March 2026: the
  repository is archived and receives no further releases or security
  fixes. An internet-facing proxy that no longer gets patches is not
  acceptable for production.
- Every LoadBalancer on EKS needs the **AWS Load Balancer Controller**
  anyway. The in-tree cloud provider's load balancer support is legacy.
  An in-cluster proxy therefore means two components to run and patch: the
  controller for the NLB, plus the proxy.
- Terraform already issues a DNS-validated wildcard **ACM certificate** for
  each environment domain, and the public subnets carry the
  `kubernetes.io/role/elb` tag.

## Decision

- Install the AWS Load Balancer Controller (chart pinned, IRSA role with the
  upstream policy) and expose OpsPilot through `Ingress` objects with
  `ingressClassName: alb`. TLS terminates at the ALB with the ACM
  certificate, which the controller finds from the Ingress hosts. Targets
  are pod IPs (`target-type: ip`), and Ingresses share one ALB through an
  ingress group.
- Install cert-manager with Let's Encrypt `ClusterIssuer`s (staging and
  production) that solve Route53 DNS-01 challenges. Its IRSA role may only
  write `_acme-challenge` TXT records in the environment's own zone. It
  issues certificates that must live in the cluster: end-to-end TLS behind
  the ALB, internal endpoints, and in-cluster controllers such as the local
  kind setup.
- The Helm chart's Ingress template stays controller-neutral (class name,
  annotations, hosts, TLS secret). The network policy takes its allowed
  ingress peers from values: the VPC CIDR for ALB IP targets, or a
  controller namespace for an in-cluster proxy.

## Consequences

- No proxy pods to patch or scale; the ALB scales and fails over across
  zones, and AWS WAF can be attached later with one annotation.
- About $16/month plus LCUs per ALB. Sharing one ingress group keeps it to
  one ALB per environment.
- ALB features replace nginx annotations. Rewrites and per-route rate
  limits are not available at the edge, so the API keeps its own rate
  limiting.
- With IP targets, traffic reaches pods from the ALB's VPC addresses, not
  from a namespace, so the network policy allows the VPC CIDR on the web and
  API ports.

## Alternatives considered

- **ingress-nginx (alone, or behind an NLB from the controller)**: rejected.
  It is retired and unpatched.
- **Another in-cluster proxy (Traefik, Envoy Gateway, NGINX Gateway Fabric)
  behind an NLB**: works with cert-manager secrets and Gateway API, but
  adds a second component next to the controller that is needed anyway.
  Worth revisiting if OpsPilot needs edge features the ALB lacks.
- **cert-manager certificates at the edge**: an ALB cannot use Kubernetes
  TLS secrets. ACM certificates renew automatically and are already
  managed by Terraform.
