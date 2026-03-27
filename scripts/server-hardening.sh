#!/usr/bin/env bash
# Delphi Press — Server Security Hardening Script
# Target: Debian 12 (Yandex Cloud VPS)
# Usage: sudo bash server-hardening.sh [step_number]
#   No argument = run all steps
#   step_number = run only that step (1-11)
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; }

# Ensure running as root
if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root (sudo bash $0)"
    exit 1
fi

STEP="${1:-all}"

# Update apt cache before anything (required for fresh servers)
apt-get update -q

# ═══════════════════════════════════════════════════════════════════════════════
# Step 1: SSH Hardening
# ═══════════════════════════════════════════════════════════════════════════════
step1_ssh() {
    log "Step 1: SSH Hardening"

    cat > /etc/ssh/sshd_config.d/99-hardening.conf << 'EOF'
# Delphi Press — SSH Hardening (CIS Debian 12 Benchmark)

# Authentication
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
PermitEmptyPasswords no
AuthenticationMethods publickey

# Access control
AllowUsers deploy
MaxAuthTries 3
MaxSessions 4
MaxStartups 10:30:60

# Session timeouts
LoginGraceTime 60
ClientAliveInterval 300
ClientAliveCountMax 2

# Disable unnecessary features
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
PermitTunnel no
PrintMotd no

# Logging
SyslogFacility AUTH
LogLevel VERBOSE

# Cryptography — modern only
KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com,umac-128-etm@openssh.com
HostKeyAlgorithms ssh-ed25519,ssh-ed25519-cert-v01@openssh.com,rsa-sha2-512,rsa-sha2-256
EOF

    # Validate config before restarting
    if sshd -t; then
        systemctl restart ssh
        log "SSH config applied and service restarted"
    else
        err "SSH config validation failed! Removing bad config."
        rm -f /etc/ssh/sshd_config.d/99-hardening.conf
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Step 2: fail2ban
# ═══════════════════════════════════════════════════════════════════════════════
step2_fail2ban() {
    log "Step 2: fail2ban"

    apt-get install -y -q fail2ban

    mkdir -p /etc/fail2ban/jail.d

    cat > /etc/fail2ban/jail.d/sshd.local << 'EOF'
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1
# Debian 12: use journald instead of /var/log/auth.log
backend  = systemd

[sshd]
enabled  = true
port     = ssh
filter   = sshd
maxretry = 3
findtime = 86400
bantime  = 86400

[recidive]
enabled   = true
logpath   = /var/log/fail2ban.log
backend   = auto
banaction = iptables-allports
bantime   = 604800
findtime  = 86400
maxretry  = 3
EOF

    systemctl enable fail2ban
    systemctl restart fail2ban
    log "fail2ban installed and configured"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Step 3: Kernel Hardening (sysctl)
# ═══════════════════════════════════════════════════════════════════════════════
step3_sysctl() {
    log "Step 3: Kernel Hardening (sysctl)"

    cat > /etc/sysctl.d/99-hardening.conf << 'EOF'
# Delphi Press — Kernel Security Hardening

# Anti-spoofing (reverse-path filtering)
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# ICMP redirects — disable
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv4.conf.all.secure_redirects = 0
net.ipv4.conf.default.secure_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0

# Source routing — disable
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0

# SYN flood protection
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 2

# TCP hardening
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_keepalive_time = 300
net.ipv4.tcp_keepalive_intvl = 60
net.ipv4.tcp_keepalive_probes = 5
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1

# Martian packet logging
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# IP forwarding — REQUIRED for Docker
net.ipv4.ip_forward = 1

# Kernel memory protection
kernel.randomize_va_space = 2
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
kernel.yama.ptrace_scope = 1
fs.suid_dumpable = 0

# Swap: prefer RAM, swap as last resort
vm.swappiness = 10
vm.vfs_cache_pressure = 50

# IPv6: disable (not used on this server)
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1
EOF

    sysctl --system > /dev/null 2>&1
    log "Kernel parameters hardened"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Step 4: Swap (4 GB)
# ═══════════════════════════════════════════════════════════════════════════════
step4_swap() {
    log "Step 4: Swap"

    if swapon --show | grep -q '/swapfile'; then
        warn "Swap already exists, skipping"
        return
    fi

    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile

    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi

    log "4 GB swap created and enabled"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Step 5: NTP Hardening (ntpsec — localhost only)
# ═══════════════════════════════════════════════════════════════════════════════
step5_ntp() {
    log "Step 5: NTP Hardening"

    NTP_CONF="/etc/ntpsec/ntp.conf"
    if [[ ! -f "$NTP_CONF" ]]; then
        warn "ntpsec config not found at $NTP_CONF, skipping"
        return
    fi

    # Backup original
    cp "$NTP_CONF" "${NTP_CONF}.bak"

    cat > "$NTP_CONF" << 'EOF'
# Delphi Press — NTPsec (localhost only)

# Yandex Cloud internal NTP + Debian pools
server 169.254.169.123 iburst prefer
pool 0.debian.pool.ntp.org iburst
pool 1.debian.pool.ntp.org iburst

# Restrict: deny all by default, allow localhost
restrict default kod nomodify notrap nopeer noquery
restrict 127.0.0.1
restrict ::1

# Only listen on loopback
interface ignore wildcard
interface listen lo

# Driftfile
driftfile /var/lib/ntpsec/ntp.drift
EOF

    systemctl restart ntpsec
    log "NTP restricted to localhost"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Step 6: Docker CE + Compose
# ═══════════════════════════════════════════════════════════════════════════════
step6_docker() {
    log "Step 6: Docker CE Installation"

    if command -v docker &>/dev/null; then
        warn "Docker already installed: $(docker --version)"
        return
    fi

    apt-get install -y -q ca-certificates curl
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    cat > /etc/apt/sources.list.d/docker.sources << 'EOF'
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: bookworm
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

    apt-get update -q
    apt-get install -y -q \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin

    # Add deploy to docker group
    usermod -aG docker deploy

    # Enable autostart
    systemctl enable docker containerd

    log "Docker CE and Compose plugin installed"
    log "NOTE: 'deploy' user must re-login for docker group to take effect"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Step 7: Docker daemon.json (hardening)
# ═══════════════════════════════════════════════════════════════════════════════
step7_docker_config() {
    log "Step 7: Docker daemon.json"

    mkdir -p /etc/docker

    cat > /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "live-restore": true,
  "no-new-privileges": true,
  "icc": false,
  "iptables": true,
  "userland-proxy": false,
  "default-ulimits": {
    "nofile": { "Name": "nofile", "Soft": 32768, "Hard": 65536 },
    "nproc": { "Name": "nproc", "Soft": 2048, "Hard": 4096 }
  },
  "log-level": "info"
}
EOF

    if systemctl is-active --quiet docker; then
        systemctl restart docker
        log "Docker daemon restarted with hardened config"
    else
        log "Docker daemon.json written (Docker not yet running)"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Step 8: Host Firewall (iptables + DOCKER-USER)
# ═══════════════════════════════════════════════════════════════════════════════
step8_firewall() {
    log "Step 8: Host Firewall (iptables)"

    # Install without interactive prompts
    echo iptables-persistent iptables-persistent/autosave_v4 boolean true | debconf-set-selections
    echo iptables-persistent iptables-persistent/autosave_v6 boolean true | debconf-set-selections
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q iptables-persistent netfilter-persistent

    # ── SAFETY: keep ACCEPT policy while building rules ──
    iptables -P INPUT ACCEPT
    iptables -P FORWARD ACCEPT
    iptables -P OUTPUT ACCEPT

    # Flush old INPUT rules
    iptables -F INPUT

    # ── Build all ACCEPT rules FIRST (while policy is still ACCEPT) ──

    # Loopback
    iptables -A INPUT -i lo -j ACCEPT

    # Established connections
    iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

    # SSH (rate limiting via fail2ban, not iptables — simpler and safer)
    iptables -A INPUT -p tcp --dport 22 -j ACCEPT

    # HTTP/HTTPS
    iptables -A INPUT -p tcp --dport 80 -j ACCEPT
    iptables -A INPUT -p tcp --dport 443 -j ACCEPT

    # ICMP ping (rate limited)
    iptables -A INPUT -p icmp --icmp-type echo-request -m limit --limit 1/s -j ACCEPT

    # ── Verify SSH rule exists before switching to DROP ──
    if iptables -C INPUT -p tcp --dport 22 -j ACCEPT 2>/dev/null; then
        iptables -P INPUT DROP
        log "INPUT policy set to DROP (SSH rule verified present)"
    else
        err "SSH ACCEPT rule NOT found! Keeping ACCEPT policy for safety."
        return 1
    fi

    # ── DOCKER-USER chain: filter Docker traffic ──
    if iptables -L DOCKER-USER -n &>/dev/null; then
        iptables -F DOCKER-USER

        iptables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
        iptables -A DOCKER-USER -s 172.16.0.0/12 -j ACCEPT
        iptables -A DOCKER-USER -d 172.16.0.0/12 -j ACCEPT
        iptables -A DOCKER-USER -p tcp -m conntrack --ctorigdstport 80 -j ACCEPT
        iptables -A DOCKER-USER -p tcp -m conntrack --ctorigdstport 443 -j ACCEPT
        iptables -A DOCKER-USER -j RETURN

        log "DOCKER-USER chain configured"
    else
        warn "DOCKER-USER chain not found (Docker not running?). Skipping."
        warn "Re-run 'sudo bash server-hardening.sh 8' after Docker starts."
    fi

    # Save rules to disk (survives reboot)
    netfilter-persistent save

    log "Host firewall configured (INPUT DROP policy, SSH/80/443 allowed)"
    log "Rules saved to /etc/iptables/rules.v4"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Step 9: Unattended Upgrades tuning
# ═══════════════════════════════════════════════════════════════════════════════
step9_unattended() {
    log "Step 9: Unattended Upgrades tuning"

    UFILE="/etc/apt/apt.conf.d/50unattended-upgrades"
    if [[ ! -f "$UFILE" ]]; then
        warn "unattended-upgrades config not found, skipping"
        return
    fi

    # Backup
    cp "$UFILE" "${UFILE}.bak"

    # Add Docker packages to blacklist if not already there
    if ! grep -q 'docker-ce' "$UFILE"; then
        # Insert blacklist entries before the closing brace of Package-Blacklist
        sed -i '/^Unattended-Upgrade::Package-Blacklist/,/};/{
            /};/i\    "linux-image-*";\n    "linux-headers-*";\n    "docker-ce";\n    "docker-ce-cli";\n    "containerd.io";
        }' "$UFILE" 2>/dev/null || true
    fi

    # Ensure no automatic reboot
    if grep -q '^Unattended-Upgrade::Automatic-Reboot' "$UFILE"; then
        sed -i 's/^Unattended-Upgrade::Automatic-Reboot.*/Unattended-Upgrade::Automatic-Reboot "false";/' "$UFILE"
    else
        echo 'Unattended-Upgrade::Automatic-Reboot "false";' >> "$UFILE"
    fi

    log "Unattended upgrades: Docker/kernel blacklisted, no auto-reboot"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Step 10: Audit Logging (auditd)
# ═══════════════════════════════════════════════════════════════════════════════
step10_auditd() {
    log "Step 10: Audit Logging (auditd)"

    apt-get install -y -q auditd
    # audispd-plugins may not exist as separate package in Debian 12
    apt-get install -y -q audispd-plugins 2>/dev/null || true

    cat > /etc/audit/rules.d/99-production.rules << 'EOF'
# Delphi Press — Production Audit Rules

# Buffer and failure mode
-b 8192
-f 1

# SSH and authentication
-w /etc/ssh/sshd_config -p wa -k sshd
-w /etc/ssh/sshd_config.d/ -p wa -k sshd
-w /etc/pam.d/ -p wa -k pam

# Identity files
-w /etc/passwd -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/group -p wa -k identity
-w /etc/sudoers -p wa -k sudoers
-w /etc/sudoers.d/ -p wa -k sudoers

# Docker
-w /usr/bin/docker -p x -k docker
-w /etc/docker/ -p wa -k docker_config

# Network config
-w /etc/hosts -p wa -k network
-w /etc/sysctl.conf -p wa -k sysctl
-w /etc/sysctl.d/ -p wa -k sysctl

# Privilege escalation
-w /usr/bin/sudo -p x -k priv_esc
-w /bin/su -p x -k priv_esc

# Cron
-w /etc/crontab -p wa -k cron
-w /etc/cron.d/ -p wa -k cron
EOF

    systemctl enable --now auditd
    augenrules --load 2>/dev/null || true

    log "auditd installed and rules loaded"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Step 11: Sudoers — scope deploy user (RUN LAST!)
# ═══════════════════════════════════════════════════════════════════════════════
step11_sudoers() {
    log "Step 11: Sudoers — restricting deploy user"

    warn "This will REPLACE deploy's sudo access with scoped permissions."
    warn "Make sure ALL other steps are complete before proceeding."

    cat > /etc/sudoers.d/deploy << 'EOF'
# Delphi Press — deploy user sudo scope
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl start docker
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop docker
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart docker
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload docker
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl status docker
deploy ALL=(ALL) NOPASSWD: /usr/bin/journalctl -u docker *
deploy ALL=(ALL) NOPASSWD: /usr/bin/netfilter-persistent save
deploy ALL=(ALL) NOPASSWD: /usr/bin/fail2ban-client status *
deploy ALL=(ALL) NOPASSWD: /usr/sbin/iptables -L *
EOF

    chmod 440 /etc/sudoers.d/deploy

    # Validate sudoers
    if visudo -c -f /etc/sudoers.d/deploy; then
        # Remove any broader sudo access for deploy
        # (Yandex Cloud default: /etc/sudoers.d/90-cloud-init-users)
        if [[ -f /etc/sudoers.d/90-cloud-init-users ]]; then
            # Only remove deploy lines, keep other users
            sed -i '/^deploy /d' /etc/sudoers.d/90-cloud-init-users
            log "Removed deploy from cloud-init sudoers"
        fi
        log "deploy user sudo scoped to operational commands only"
    else
        err "Sudoers validation failed! Removing bad config."
        rm -f /etc/sudoers.d/deploy
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Step 12: Let's Encrypt (Certbot standalone)
# ═══════════════════════════════════════════════════════════════════════════════
step12_certbot() {
    local DOMAIN="${2:-delphi.antopkin.ru}"
    local EMAIL="${3:-oleg.antopkin@icloud.com}"

    log "Step 12: Let's Encrypt for ${DOMAIN}"

    # Install certbot
    apt-get install -y -q certbot

    # Check if cert already exists
    if [[ -d "/etc/letsencrypt/live/${DOMAIN}" ]]; then
        warn "Certificate for ${DOMAIN} already exists. Skipping issuance."
        certbot certificates
        return
    fi

    # Standalone mode: certbot starts its own HTTP server on port 80
    # Port 80 must be free (no nginx running)
    if ss -tlnp | grep -q ':80 '; then
        err "Port 80 is in use! Stop nginx/other service first."
        ss -tlnp | grep ':80 '
        return 1
    fi

    certbot certonly \
        --standalone \
        --non-interactive \
        --agree-tos \
        --email "${EMAIL}" \
        --domain "${DOMAIN}" \
        --preferred-challenges http

    if [[ $? -eq 0 ]]; then
        log "Certificate issued for ${DOMAIN}"
        log "Cert: /etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
        log "Key:  /etc/letsencrypt/live/${DOMAIN}/privkey.pem"

        # Setup auto-renewal hook to reload nginx (when deployed)
        mkdir -p /etc/letsencrypt/renewal-hooks/deploy
        cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh << 'HOOK'
#!/bin/bash
# Reload nginx inside Docker after cert renewal
if command -v docker &>/dev/null && docker ps -q --filter name=nginx | grep -q .; then
    docker exec $(docker ps -q --filter name=nginx) nginx -s reload
fi
HOOK
        chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

        # Verify renewal timer is active
        systemctl enable --now certbot.timer
        log "Certbot auto-renewal timer enabled"

        # Test renewal
        certbot renew --dry-run && log "Renewal dry-run passed" || warn "Renewal dry-run failed"
    else
        err "Certificate issuance failed!"
        return 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Verification
# ═══════════════════════════════════════════════════════════════════════════════
verify() {
    echo ""
    echo "═══════════════════════════════════════════════"
    echo "  VERIFICATION"
    echo "═══════════════════════════════════════════════"

    echo -n "SSH hardening:    "
    [[ -f /etc/ssh/sshd_config.d/99-hardening.conf ]] && echo -e "${GREEN}OK${NC}" || echo -e "${RED}MISSING${NC}"

    echo -n "fail2ban:         "
    systemctl is-active --quiet fail2ban && echo -e "${GREEN}ACTIVE${NC}" || echo -e "${RED}INACTIVE${NC}"

    echo -n "sysctl rp_filter: "
    [[ $(sysctl -n net.ipv4.conf.all.rp_filter) == "1" ]] && echo -e "${GREEN}OK${NC}" || echo -e "${RED}FAIL${NC}"

    echo -n "Swap:             "
    swapon --show | grep -q '/swapfile' && echo -e "${GREEN}$(free -h | awk '/Swap/{print $2}')${NC}" || echo -e "${RED}MISSING${NC}"

    echo -n "NTP localhost:    "
    ss -ulnp | grep -q '127.0.0.1:123' && echo -e "${GREEN}OK${NC}" || echo -e "${YELLOW}CHECK${NC}"

    echo -n "Docker:           "
    command -v docker &>/dev/null && echo -e "${GREEN}$(docker --version 2>/dev/null | cut -d' ' -f3)${NC}" || echo -e "${RED}NOT INSTALLED${NC}"

    echo -n "daemon.json:      "
    [[ -f /etc/docker/daemon.json ]] && echo -e "${GREEN}OK${NC}" || echo -e "${RED}MISSING${NC}"

    echo -n "Firewall INPUT:   "
    iptables -L INPUT -n 2>/dev/null | grep -q 'DROP' && echo -e "${GREEN}DROP policy${NC}" || echo -e "${RED}NO POLICY${NC}"

    echo -n "auditd:           "
    systemctl is-active --quiet auditd && echo -e "${GREEN}ACTIVE${NC}" || echo -e "${RED}INACTIVE${NC}"

    echo -n "TLS cert:         "
    [[ -f /etc/letsencrypt/live/delphi.antopkin.ru/fullchain.pem ]] && echo -e "${GREEN}OK${NC}" || echo -e "${YELLOW}NOT YET${NC}"

    echo -n "Certbot timer:    "
    systemctl is-active --quiet certbot.timer && echo -e "${GREEN}ACTIVE${NC}" || echo -e "${YELLOW}INACTIVE${NC}"

    echo ""
    echo "Listening TCP ports:"
    ss -tlnp | grep LISTEN
    echo ""
    echo "Listening UDP ports:"
    ss -ulnp
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════
case "$STEP" in
    1)  step1_ssh ;;
    2)  step2_fail2ban ;;
    3)  step3_sysctl ;;
    4)  step4_swap ;;
    5)  step5_ntp ;;
    6)  step6_docker ;;
    7)  step7_docker_config ;;
    8)  step8_firewall ;;
    9)  step9_unattended ;;
    10) step10_auditd ;;
    11) step11_sudoers ;;
    12) step12_certbot "$@" ;;
    verify) verify ;;
    all)
        step1_ssh
        step2_fail2ban
        step3_sysctl
        step4_swap
        step5_ntp
        step6_docker
        step7_docker_config
        step8_firewall
        step9_unattended
        step10_auditd
        # Step 11 (sudoers restriction) is NOT run automatically.
        # Run manually: sudo bash server-hardening.sh 11
        warn "Step 11 (sudoers restriction) skipped — run manually after verifying everything works."
        echo ""
        verify
        ;;
    *)
        echo "Usage: sudo bash $0 [1-11|verify|all]"
        echo "  all    — run steps 1-10 + verify (step 11 manual)"
        echo "  1-11   — run specific step"
        echo "  verify — run verification checks"
        exit 1
        ;;
esac
