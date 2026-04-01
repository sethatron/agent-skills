# Network Address Translation (NAT)

NAT translates private IP addresses to public addresses for internet communication.

## Types of NAT

### Static NAT
One-to-one mapping between private and public addresses.

### Dynamic NAT
Maps private addresses to a pool of public addresses.

### PAT (Port Address Translation)
Multiple private addresses share one public address using port numbers.

## Configuration Example

```
ip nat inside source static 192.168.1.10 203.0.113.10
interface GigabitEthernet0/0
  ip nat inside
interface GigabitEthernet0/1
  ip nat outside
```

## Key Concepts

| Term | Description |
|------|-------------|
| Inside Local | Private IP on internal network |
| Inside Global | Public IP representing internal host |
| Outside Global | Public IP of external destination |
