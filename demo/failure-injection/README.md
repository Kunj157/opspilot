# Failure injection

Every scenario ships a **faulty release**: a new rollout revision of one demo
deployment with a bumped `SERVICE_VERSION`, fault settings, and a
`kubernetes.io/change-cause` annotation. That is what a bad deploy looks
like to OpsPilot, and `kubectl rollout undo` (the remediation it proposes)
removes it.

```bash
make load-normal                              # steady traffic (RPS=5 by default)
make inject-failure SCENARIO=checkout-http-500
make reset-demo                               # back to the healthy chart release
make load-stop
```

| Scenario | Release | Effect |
|---|---|---|
| `checkout-http-500` | checkout 1.4.2 | 50% of checkout requests fail with 500; storefront checkouts return 502 |
| `checkout-latency` | checkout 1.4.3 | +900 ms on every checkout request |
| `payment-timeout` | payment 2.1.0 | +3 s on payment, past checkout's 2 s timeout, so checkouts fail with 502 |
| `inventory-http-500` | inventory 1.2.1 | 30% of inventory requests fail; browsing and checkout both degrade |

Scenarios are defined in `scenarios.env` and applied by
`scripts/inject-failure.sh`. The script prints a UTC timestamp for the
injection, to measure detection delay.

Measured locally with 5 rps of load: after `checkout-http-500`, the
checkout error rate reached 0.54 and storefront 0.14 within a minute. After
`make reset-demo`, all services were back to 0.
