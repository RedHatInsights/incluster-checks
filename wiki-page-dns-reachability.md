# Network ‐ Verify DNS reachability

## Description

This rule verifies that DNS servers are reachable from all cluster nodes. The rule first checks for upstream DNS resolvers configured in the OpenShift DNS operator. If no upstream resolvers are found, it falls back to checking `/etc/resolv.conf` on each node. The rule then tests connectivity to each DNS server by pinging it from every node and reports any unreachable DNS servers.

**Severity:** High - DNS connectivity is critical for cluster operations

**What is checked:**
- OpenShift DNS operator upstream resolver configuration (`dns.operator.openshift.io/cluster`)
- Nameserver entries in `/etc/resolv.conf` on each node (if no upstream resolvers configured)
- ICMP (ping) connectivity to each DNS server from all nodes

## Prerequisites

- OpenShift cluster with network connectivity
- `ping` command available on nodes
- ICMP traffic allowed between nodes and DNS servers (firewall rules)
- Read access to DNS operator configuration (for upstream resolver check)

## Impact

Unreachable DNS servers can cause severe cluster disruption:

- **Pod startup failures** - Pods cannot resolve service names or external hostnames during initialization
- **Service discovery failures** - Kubernetes service DNS lookups fail, breaking inter-pod communication
- **Image pull failures** - Cannot resolve container registry hostnames (e.g., quay.io, registry.redhat.io)
- **Operator failures** - OpenShift operators cannot reach external APIs or update channels
- **Application errors** - Applications cannot resolve external dependencies (databases, APIs, webhooks)
- **Cluster upgrades blocked** - Cannot reach Red Hat update servers
- **Certificate renewal failures** - ACME challenges and external CA validation fail
- **Node NotReady state** - kubelet and container runtime may report issues if DNS is unavailable

**Critical Note:** Even if some DNS servers are reachable, having unreachable servers can cause intermittent failures and increased latency due to DNS timeout retries.

## Root Cause

DNS servers may become unreachable due to:

- **Network connectivity issues**
  - Firewall rules blocking ICMP or DNS traffic (port 53)
  - Network interface down on DNS server
  - Routing problems between cluster nodes and DNS servers
  - Network partition or split-brain scenario

- **DNS server issues**
  - DNS server process stopped or crashed
  - DNS server overloaded or unresponsive
  - DNS server host powered off or rebooted

- **Configuration issues**
  - Incorrect DNS server IP addresses in configuration
  - Stale DNS configuration after infrastructure changes
  - Mismatch between upstream resolvers and actual DNS infrastructure

- **Infrastructure changes**
  - DNS servers migrated to new IPs without updating cluster config
  - DNS infrastructure decommissioned
  - Network topology changes (VLAN, subnet, gateway changes)

## Diagnostics

### Check DNS Configuration

**Check upstream DNS resolvers in DNS operator:**
```bash
# Check if upstream DNS resolvers are configured
oc get dns.operator.openshift.io/cluster -o jsonpath='{.spec.upstreamResolvers}'

# View full DNS operator configuration
oc get dns.operator.openshift.io/cluster -o yaml
```

**Check /etc/resolv.conf on nodes:**
```bash
# View DNS configuration on a specific node
oc debug node/<node-name>
chroot /host
cat /etc/resolv.conf
```

### Test DNS Connectivity

**Ping DNS servers from nodes:**
```bash
# On each node, ping the DNS servers
oc debug node/<node-name>
chroot /host

# Ping IPv4 DNS server
ping -c 3 -W 2 <dns-server-ip>

# Ping IPv6 DNS server
ping -6 -c 3 -W 2 <dns-server-ipv6>
```

**Test DNS resolution:**
```bash
# Test if DNS queries work (not just ping)
oc debug node/<node-name>
chroot /host

# Test DNS query using dig
dig @<dns-server-ip> google.com

# Test DNS query using nslookup
nslookup google.com <dns-server-ip>

# Test DNS query using host
host google.com <dns-server-ip>
```

**Check network connectivity:**
```bash
# Check routing to DNS server
oc debug node/<node-name>
chroot /host
ip route get <dns-server-ip>

# Check if DNS port 53 is reachable (TCP)
nc -zv <dns-server-ip> 53

# Check if DNS port 53 is reachable (UDP)
nc -zvu <dns-server-ip> 53
```

### Check CoreDNS Status

**Check OpenShift DNS pods:**
```bash
# Check DNS pods status
oc get pods -n openshift-dns

# Check DNS pod logs
oc logs -n openshift-dns <dns-pod-name>

# Check if DNS service is working
oc get service -n openshift-dns

# Test DNS from inside cluster
oc run -it --rm debug-dns --image=registry.access.redhat.com/ubi9/ubi:latest --restart=Never -- nslookup kubernetes.default
```

## Solution

### 1. Fix Network Connectivity

If DNS servers are unreachable due to network issues:

```bash
# Check firewall rules allow DNS traffic
# On RHEL/RHCOS nodes:
oc debug node/<node-name>
chroot /host

# Check firewall status
systemctl status firewalld
firewall-cmd --list-all

# If needed, add firewall rule (not recommended - fix upstream firewall instead)
# firewall-cmd --permanent --add-service=dns
# firewall-cmd --reload
```

**Better approach:** Fix firewall rules on the network infrastructure (routers, firewalls) to allow:
- ICMP (ping) from cluster nodes to DNS servers
- UDP port 53 from cluster nodes to DNS servers
- TCP port 53 from cluster nodes to DNS servers

### 2. Update DNS Configuration

If DNS server IPs are wrong or stale:

**Update upstream DNS resolvers in DNS operator:**
```bash
# Edit DNS operator configuration
oc edit dns.operator.openshift.io/cluster

# Add or update upstream resolvers:
spec:
  upstreamResolvers:
    upstreams:
    - type: Network
      address: 192.168.1.1  # Your correct DNS server IP
      port: 53
    - type: Network
      address: 8.8.8.8      # Backup DNS server
      port: 53
```

**Update /etc/resolv.conf via MachineConfig (if needed):**
```yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  labels:
    machineconfiguration.openshift.io/role: worker
  name: 99-worker-dns
spec:
  config:
    ignition:
      version: 3.2.0
    storage:
      files:
      - path: /etc/resolv.conf
        mode: 0644
        overwrite: true
        contents:
          inline: |
            search cluster.local
            nameserver 192.168.1.1
            nameserver 8.8.8.8
```

**Warning:** Only use MachineConfig for DNS changes if absolutely necessary, as it will reboot nodes. Prefer configuring upstream resolvers in the DNS operator.

### 3. Restart DNS Services

If DNS servers are running but unresponsive:

**On the DNS server infrastructure (not cluster nodes):**
```bash
# Restart DNS service (depends on your DNS server - examples):
# For BIND:
systemctl restart named

# For dnsmasq:
systemctl restart dnsmasq

# For systemd-resolved:
systemctl restart systemd-resolved
```

**Restart CoreDNS in OpenShift (if internal DNS is the issue):**
```bash
# Restart DNS pods
oc delete pods -n openshift-dns --all

# Wait for new pods to start
oc get pods -n openshift-dns -w
```

### 4. Verify Fix

After applying fixes, verify DNS is working:

```bash
# Re-run the in-cluster-checks rule
in-cluster-checks --debug-rule verify_dns_reachability

# Or test manually from a node
oc debug node/<node-name>
chroot /host
ping -c 3 <dns-server-ip>
nslookup google.com
```

## Resources

- [OpenShift DNS Operator Documentation](https://docs.openshift.com/container-platform/latest/networking/dns-operator.html)
- [Configuring DNS forwarding in OpenShift](https://docs.openshift.com/container-platform/latest/networking/dns-operator.html#nw-dns-forward_dns-operator)
- [Troubleshooting DNS in OpenShift](https://docs.openshift.com/container-platform/latest/support/troubleshooting/troubleshooting-network-issues.html#nw-troubleshoot-dns_troubleshooting-network-issues)
- [Red Hat KB: Debugging DNS resolution](https://access.redhat.com/solutions/3804501)
