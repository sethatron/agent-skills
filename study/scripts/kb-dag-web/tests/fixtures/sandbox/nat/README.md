# NAT Sandbox Project

Build a NAT gateway using iptables.

## Objectives

- Configure SNAT for outbound traffic
- Set up DNAT for port forwarding
- Test connectivity between network segments

## Getting Started

Run the setup script:

```bash
./setup.sh
```

Then verify NAT rules with `iptables -t nat -L`.
