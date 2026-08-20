# Assessment Implementasi ERP PT. Kain Nusantara
## **COMPREHENSIVE EDITION — Part 3 (Domain 7-15) FINAL**

---

# DOMAIN 7 — Infrastructure & Network Architecture ⚡

> **Assessment Goal:** Ensure infrastructure dapat support ERP operations dengan reliability, performance, dan scalability yang adequate untuk 3-5 tahun ke depan.

## 7.1 Server & Hosting Strategy

### 7.1.1 Hosting Model Decision

**Compare Options:**

| Criteria | On-Premise | Cloud (IaaS) | Cloud (SaaS) | Hybrid | Recommended? |
|----------|------------|--------------|--------------|--------|--------------|
| **Initial Cost** | High (CapEx) | Low (OpEx) | Medium (OpEx) | Medium | |
| **Scalability** | Limited | High | Very High | High | |
| **Control** | Full control | Medium | Low | Medium | |
| **Maintenance** | Internal team | Shared | Vendor | Shared | |
| **Customization** | Full | Full | Limited | Full | |
| **Security** | Full control | Shared responsibility | Vendor | Shared | |
| **Disaster Recovery** | Manual setup | Built-in | Built-in | Built-in | |
| **Compliance** | Full control | Need audit | Need audit | Medium | |
| **Internet Dependency** | Low | High | Very High | Medium | |
| **Best for PT. KN?** | ☐ | ☑ **Yes (Recommended)** | ☐ | ☐ |

**Recommendation untuk PT. Kain Nusantara: Cloud IaaS (Infrastructure as a Service)**

✅ **Alasan:**
- Scalability for business growth
- Built-in backup & disaster recovery
- Lower initial investment
- Professional managed services
- Pay-as-you-grow model
- 99.9% uptime SLA

**Recommended Cloud Provider:**
- **Primary choice:** AWS / Google Cloud / Azure
- **Local option:** Biznet Gio / IDCloudHost (jika prefer local support)

### 7.1.2 Server Sizing Calculation ⚡

**Workload Analysis:**

| Workload Type | Concurrent Users | Transactions/Day | Data Volume | Resource Requirement |
|---------------|------------------|------------------|-------------|----------------------|
| **Web Application** | 50-100 users | 5,000 transactions | — | 4-8 vCPU, 16-32GB RAM |
| **Database** | Backend | 10,000 queries | 500GB → 2TB (3 years) | 8-16 vCPU, 32-64GB RAM |
| **File Storage** | All users | 1,000 files/day | 1TB → 5TB (3 years) | Block storage |
| **RFID Middleware** | 20 devices | 50,000 scans/day | 100GB/year | 2-4 vCPU, 8GB RAM |
| **Background Jobs** | System | 100 jobs/hour | — | 2 vCPU, 4GB RAM |

**Server Specification Recommendation:**

| Server Role | Specification | Qty | Cloud Instance Type | Monthly Cost (est.) | Status |
|-------------|--------------|-----|---------------------|---------------------|--------|
| **Application Server** | 8 vCPU, 32GB RAM, 100GB SSD | 2 | AWS: t3.2xlarge / GCP: n2-standard-8 | ~Rp 12 juta | ☐ |
| **Database Server** | 16 vCPU, 64GB RAM, 1TB SSD | 1 | AWS: r6i.4xlarge / GCP: n2-highmem-16 | ~Rp 18 juta | ☐ |
| **File Storage** | 2TB block storage (scalable) | 1 | AWS: EBS / GCP: Persistent Disk | ~Rp 3 juta | ☐ |
| **Backup Storage** | 3TB object storage | 1 | AWS: S3 / GCP: Cloud Storage | ~Rp 1.5 juta | ☐ |
| **Load Balancer** | Managed service | 1 | AWS: ALB / GCP: Cloud Load Balancing | ~Rp 1 juta | ☐ |
| **Monitoring** | Managed service | 1 | AWS: CloudWatch / GCP: Cloud Monitoring | ~Rp 500k | ☐ |
| **Total Monthly** | | | | **~Rp 36 juta/month** | ☐ |

**Annual Infrastructure Cost:** ~Rp 430 juta/year

**Scalability Plan:**
- Year 1: Start with spec above (50-100 users)
- Year 2: Scale to 150 users (+50% resources) → ~Rp 54 juta/month
- Year 3: Scale to 250 users (+100% resources) → ~Rp 72 juta/month

### 7.1.3 Database Architecture ⚡

**Primary Database: MongoDB (already chosen)**

| Aspect | Configuration | Specification | Status |
|--------|---------------|---------------|--------|
| **Deployment Model** | Replica Set (3 nodes) | Primary-Secondary-Secondary | ☐ |
| **Version** | MongoDB 7.0+ | Latest stable | ☐ |
| **Storage Engine** | WiredTiger | Default | ☐ |
| **Initial Size** | 500GB | Scalable to 5TB | ☐ |
| **Backup Strategy** | Automated daily snapshots | Retention: 30 days | ☐ |
| **Point-in-Time Recovery** | Enabled | RPO: 5 minutes | ☐ |
| **Monitoring** | MongoDB Atlas / Cloud Monitoring | Real-time alerts | ☐ |

**Database Performance Optimization:**

| Optimization | Implementation | Impact | Status |
|--------------|----------------|--------|--------|
| **Indexing Strategy** | Compound indexes on frequently queried fields | Query speed ↑ 10-100x | ☐ |
| **Sharding** | Horizontal scaling (if needed in future) | Handle >10TB data | ☐ Future |
| **Read Replicas** | Secondary nodes for reporting queries | Reduce primary load | ☐ |
| **Connection Pooling** | Max 100 connections per app server | Efficient resource use | ☐ |
| **Query Optimization** | Regular slow query analysis | Maintain <100ms avg | ☐ |

**Data Growth Projection:**

| Year | Transactions/Year | Data Growth | Cumulative Size | Monthly Cost | Status |
|------|-------------------|-------------|-----------------|--------------|--------|
| Year 1 | 100K transactions | 200GB | 500GB | Rp 1.5 juta | ☐ |
| Year 2 | 150K transactions | 300GB | 800GB | Rp 2.4 juta | ☐ |
| Year 3 | 250K transactions | 500GB | 1.3TB | Rp 3.9 juta | ☐ |
| Year 5 | 500K transactions | 1TB | 2.8TB | Rp 8.4 juta | ☐ |

## 7.2 Network Architecture & Connectivity

### 7.2.1 Network Topology Design

**Recommended Network Architecture:**

```
                        ┌─────────────────────┐
                        │   Internet (ISP)    │
                        │  Primary: 100 Mbps  │
                        │  Backup: 50 Mbps    │
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │  Firewall (UTM)     │
                        │  • Sophos / Fortinet│
                        │  • IPS/IDS          │
                        │  • VPN Gateway      │
                        └──────────┬──────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                │                  │                  │
        ┌───────▼────────┐  ┌─────▼──────┐  ┌──────▼───────┐
        │ DMZ Zone       │  │ LAN Zone   │  │ Warehouse    │
        │ • Web Server   │  │ • Clients  │  │ Zone (WiFi)  │
        │ • VPN Gateway  │  │ • Printers │  │ • RFID       │
        └────────────────┘  └────────────┘  │ • Handheld   │
                                             └──────────────┘
```

### 7.2.2 Internet Connectivity Requirements

| Location | Type | Bandwidth Required | Recommended Provider | Backup Connection | Monthly Cost | Status |
|----------|------|-------------------|---------------------|-------------------|--------------|--------|
| **Head Office** | Primary | 100 Mbps (dedicated) | Biznet / First Media / Telkom | 4G LTE router | Rp 3 juta | ☐ |
| **Head Office** | Backup | 4G LTE (unlimited) | Telkomsel / Indosat | — | Rp 500k | ☐ |
| **Warehouse 1** | Primary | 50 Mbps | Local ISP | 4G LTE | Rp 2 juta | ☐ |
| **Warehouse 2** | Primary | 50 Mbps | Local ISP | 4G LTE | Rp 2 juta | ☐ |
| **Branch Office** | Primary | 50 Mbps | Local ISP | 4G LTE | Rp 2 juta | ☐ |

**Total Internet Cost:** ~Rp 10 juta/month

**Critical Requirement:**
- ✅ **Uptime SLA:** ≥ 99.5% (max downtime 3.6 jam/month)
- ✅ **Latency:** ≤ 50ms to cloud server
- ✅ **Automatic failover:** Switch to backup within 30 seconds

### 7.2.3 WiFi Coverage Planning (Warehouse) ⚡

**Critical untuk RFID Handheld Operation**

| Warehouse | Size (m²) | Access Points Needed | Coverage Standard | Dead Zones | Status |
|-----------|----------|----------------------|-------------------|------------|--------|
| Warehouse 1 | 2,000 m² | 8 APs | ≥ -65 dBm | Zero | ☐ |
| Warehouse 2 | 1,500 m² | 6 APs | ≥ -65 dBm | Zero | ☐ |
| Warehouse 3 | 1,000 m² | 4 APs | ≥ -65 dBm | Zero | ☐ |

**WiFi Specification:**

| Specification | Requirement | Recommended Model | Qty | Cost per Unit | Status |
|---------------|-------------|-------------------|-----|---------------|--------|
| **WiFi Standard** | WiFi 6 (802.11ax) | Ubiquiti UniFi 6 / Ruckus R650 | 18 APs | Rp 4 juta | ☐ |
| **Frequency** | Dual-band 2.4GHz + 5GHz | | | | ☐ |
| **Speed** | ≥ 1.2 Gbps | | | | ☐ |
| **Clients per AP** | Support 50+ clients | | | | ☐ |
| **Roaming** | Seamless roaming | | | | ☐ |
| **Management** | Centralized controller | UniFi Controller | 1 | Included | ☐ |
| **Power** | PoE+ (802.3at) | | | | ☐ |

**WiFi Site Survey:**
- ⚠️ **MANDATORY:** Conduct site survey before installation
- ⚠️ Check for interference (metal racks, machinery)
- ⚠️ Validate coverage with heatmap tool
- ✅ **Success criteria:** ≥ -65 dBm in 100% warehouse area

### 7.2.4 Network Equipment List

| Equipment | Specification | Qty | Unit Cost | Total Cost | Status |
|-----------|---------------|-----|-----------|------------|--------|
| **Core Switch** | 24-port Gigabit managed switch | 3 | Rp 8 juta | Rp 24 juta | ☐ |
| **Access Switch** | 24-port Gigabit managed switch | 5 | Rp 5 juta | Rp 25 juta | ☐ |
| **Router** | Enterprise router with VPN | 3 | Rp 10 juta | Rp 30 juta | ☐ |
| **Firewall (UTM)** | Sophos XG / Fortinet 60F | 3 | Rp 25 juta | Rp 75 juta | ☐ |
| **WiFi Access Point** | UniFi 6 / Ruckus | 18 | Rp 4 juta | Rp 72 juta | ☐ |
| **WiFi Controller** | Cloud-managed | 1 | Rp 5 juta | Rp 5 juta | ☐ |
| **UPS** | 3KVA online UPS | 3 | Rp 15 juta | Rp 45 juta | ☐ |
| **Cable & Installation** | Cat6 cabling | Lump sum | — | Rp 30 juta | ☐ |
| **Total Network Infrastructure** | | | | **Rp 306 juta** | ☐ |

## 7.3 Backup & Disaster Recovery (DR) Strategy ⚡⚡

### 7.3.1 Backup Strategy

**3-2-1 Backup Rule:**
- **3** copies of data
- **2** different media types
- **1** off-site backup

| Backup Type | Frequency | Retention | Storage Location | Recovery Time | Status |
|-------------|-----------|-----------|------------------|---------------|--------|
| **Full Backup** | Weekly (Sunday night) | 4 weeks | Cloud storage | 4-6 hours | ☐ |
| **Incremental Backup** | Daily (midnight) | 7 days | Cloud storage | 2-4 hours | ☐ |
| **Transaction Log** | Every 15 minutes | 7 days | Cloud storage | <1 hour (point-in-time) | ☐ |
| **Off-site Backup** | Weekly | 12 months | Different region | 6-8 hours | ☐ |
| **Critical Data Snapshot** | Hourly | 24 hours | Cloud storage | <30 minutes | ☐ |

**Backup Automation:**
- ✅ Automated via cloud provider (AWS Backup / GCP Backup)
- ✅ Backup verification (automated test restore monthly)
- ✅ Alert on backup failure

### 7.3.2 Disaster Recovery Plan

**Recovery Objectives:**

| Metric | Target | Definition | Status |
|--------|--------|------------|--------|
| **RTO (Recovery Time Objective)** | ≤ 4 hours | Max downtime acceptable | ☐ |
| **RPO (Recovery Point Objective)** | ≤ 15 minutes | Max data loss acceptable | ☐ |
| **MTTR (Mean Time to Repair)** | ≤ 2 hours | Average time to fix issues | ☐ |

**DR Scenarios & Response:**

| Disaster Scenario | Probability | Impact | Recovery Strategy | Recovery Time | Status |
|-------------------|-------------|--------|-------------------|---------------|--------|
| **Server Hardware Failure** | Medium | High | Failover to standby server | <30 minutes | ☐ |
| **Database Corruption** | Low | Critical | Restore from last backup | 2-4 hours | ☐ |
| **Ransomware Attack** | Medium | Critical | Restore from clean backup | 4-8 hours | ☐ |
| **Data Center Failure** | Very Low | Critical | Failover to DR region | 4-6 hours | ☐ |
| **Internet Outage** | Medium | High | Failover to backup ISP | <5 minutes | ☐ |
| **Power Outage** | Medium | Medium | UPS → Generator (if available) | <1 minute | ☐ |
| **Natural Disaster** | Very Low | Critical | DR site activation | 6-12 hours | ☐ |

**DR Testing Schedule:**

| Test Type | Frequency | Participants | Success Criteria | Status |
|-----------|-----------|--------------|------------------|--------|
| **Backup Restore Test** | Monthly | IT team | Successful restore of sample data | ☐ |
| **Failover Test** | Quarterly | IT + Key users | <30 min failover, all services up | ☐ |
| **Full DR Drill** | Annually | All stakeholders | Meet RTO/RPO targets | ☐ |

### 7.3.3 Business Continuity Plan (BCP)

**Critical Business Functions:**

| Function | Maximum Tolerable Downtime | Recovery Priority | Workaround if System Down | Status |
|----------|----------------------------|-------------------|---------------------------|--------|
| **Sales Order Entry** | 2 hours | P1 (Critical) | Manual form + re-entry later | ☐ |
| **Goods Receipt** | 4 hours | P1 (Critical) | Manual log + update later | ☐ |
| **Inventory Query** | 4 hours | P2 (High) | Use last export report | ☐ |
| **Picking & Packing** | 2 hours | P1 (Critical) | Manual pick list (print backup) | ☐ |
| **Financial Reporting** | 1 day | P3 (Medium) | Manual calculation | ☐ |
| **RFID Scanning** | 4 hours | P2 (High) | Fallback to barcode/manual | ☐ |

**BCP Communication Plan:**

| Role | Contact Person | Phone | Email | Responsibility | Status |
|------|----------------|-------|-------|----------------|--------|
| **BCP Coordinator** | [Name] | [Phone] | [Email] | Overall coordination | ☐ |
| **IT Recovery Lead** | [Name] | [Phone] | [Email] | Technical recovery | ☐ |
| **Business Recovery Lead** | [Name] | [Phone] | [Email] | Business operations | ☐ |
| **Communication Lead** | [Name] | [Phone] | [Email] | Stakeholder communication | ☐ |

## 7.4 Infrastructure Monitoring & Performance

### 7.4.1 Monitoring Requirements

**What to Monitor:**

| Component | Metrics | Alert Threshold | Alert Channel | Status |
|-----------|---------|-----------------|---------------|--------|
| **Application Server** | CPU, Memory, Disk, Response time | CPU >80%, Response >2s | Email + SMS | ☐ |
| **Database Server** | CPU, Memory, Disk, Query time | CPU >70%, Query >100ms | Email + SMS | ☐ |
| **Network** | Bandwidth, Latency, Packet loss | Latency >100ms, Loss >1% | Email | ☐ |
| **Storage** | Disk usage, I/O latency | Usage >80%, Latency >10ms | Email | ☐ |
| **Backup Jobs** | Job status, Duration | Job failed, Duration >2x normal | Email + SMS | ☐ |
| **Application Errors** | Error rate, Crash rate | Error >1%, Crash any | Email + SMS + Slack | ☐ |
| **Security Events** | Failed login, Intrusion attempt | >5 failed login, Any intrusion | Email + SMS | ☐ |

**Monitoring Dashboard:**
- Real-time dashboard for IT team
- Weekly automated report to management
- Monthly capacity planning report

### 7.4.2 Performance Benchmarks

**Target Performance:**

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Page Load Time** | ≤ 2 seconds | Browser DevTools | ☐ |
| **API Response Time (avg)** | ≤ 100ms | APM tool | ☐ |
| **API Response Time (95th percentile)** | ≤ 500ms | APM tool | ☐ |
| **Database Query Time (avg)** | ≤ 50ms | MongoDB profiler | ☐ |
| **Concurrent Users Supported** | ≥ 100 users | Load testing | ☐ |
| **System Uptime** | ≥ 99.5% | Monitoring tool | ☐ |
| **RFID Scan Response** | ≤ 1 second | Field testing | ☐ |

---

# DOMAIN 8 — Security, Compliance & Governance ⚡⚡

> **Assessment Goal:** Ensure sistem secure, compliant dengan regulasi, dan memiliki proper governance framework untuk protect business-critical data.

## 8.1 Cybersecurity Framework

### 8.1.1 Security Architecture

**Defense in Depth Strategy:**

```
Layer 7: User Awareness Training
Layer 6: Application Security (Input validation, OWASP Top 10)
Layer 5: Authentication & Authorization (MFA, RBAC)
Layer 4: Endpoint Security (Antivirus, EDR)
Layer 3: Network Security (Firewall, IDS/IPS)
Layer 2: Data Encryption (At rest, In transit)
Layer 1: Physical Security (Access control, CCTV)
```

### 8.1.2 Authentication & Authorization ⚡

**Authentication Requirements:**

| Method | Implementation | Mandatory For | Status |
|--------|----------------|---------------|--------|
| **Username + Password** | Minimum 8 chars, complexity rule | All users | ☐ |
| **Multi-Factor Authentication (MFA)** | SMS OTP / Authenticator app | Admin, Finance users | ☐ |
| **Session Timeout** | 30 minutes inactive | All users | ☐ |
| **Password Expiry** | 90 days | All users | ☐ |
| **Password History** | Cannot reuse last 5 passwords | All users | ☐ |
| **Account Lockout** | 5 failed attempts → lock 30 minutes | All users | ☐ |
| **Single Sign-On (SSO)** | Optional future enhancement | — | ☐ Future |

**Authorization Model: Role-Based Access Control (RBAC)**

| Role | Modules Access | Create | Read | Update | Delete | Approve | Admin | Status |
|------|----------------|--------|------|--------|--------|---------|-------|--------|
| **Admin** | All | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ☐ |
| **Finance Director** | Finance, Sales, Purchase | ✓ | ✓ | ✓ | ☐ | ✓ | ☐ | ☐ |
| **Finance Staff** | Finance | ✓ | ✓ | ✓ | ☐ | ☐ | ☐ | ☐ |
| **Sales Director** | Sales, Customer, Inventory (view) | ✓ | ✓ | ✓ | ☐ | ✓ | ☐ | ☐ |
| **Sales** | Sales, Customer (limited), Inventory (view) | ✓ | ✓ | ✓ (own) | ☐ | ☐ | ☐ | ☐ |
| **Warehouse Manager** | Warehouse, Inventory, WMS | ✓ | ✓ | ✓ | ☐ | ✓ | ☐ | ☐ |
| **Warehouse Staff** | Warehouse (limited), Inventory (view) | ✓ (task) | ✓ | ✓ (task) | ☐ | ☐ | ☐ | ☐ |
| **Purchasing Manager** | Purchase, Supplier, Inventory (view) | ✓ | ✓ | ✓ | ☐ | ✓ | ☐ | ☐ |
| **Purchasing Staff** | Purchase, Supplier | ✓ | ✓ | ✓ (own) | ☐ | ☐ | ☐ | ☐ |
| **Production Manager** | Production, Inventory, BOM | ✓ | ✓ | ✓ | ☐ | ✓ | ☐ | ☐ |
| **Production Staff** | Production (limited) | ✓ (task) | ✓ | ✓ (task) | ☐ | ☐ | ☐ | ☐ |
| **Auditor (Read-only)** | All | ☐ | ✓ | ☐ | ☐ | ☐ | ☐ | ☐ |

**Approval Authority Matrix (Cross-reference to Section 3):**

*Detailed approval matrix sudah didefinisikan di Domain 3 per business process*

### 8.1.3 Data Encryption

| Data Type | Encryption Method | Key Management | Status |
|-----------|-------------------|----------------|--------|
| **Data at Rest (Database)** | AES-256 encryption | Cloud KMS | ☐ |
| **Data in Transit (API)** | TLS 1.3 | Let's Encrypt / DigiCert | ☐ |
| **Backup Data** | AES-256 encryption | Separate encryption key | ☐ |
| **Password Storage** | bcrypt / Argon2 hashing | N/A (one-way hash) | ☐ |
| **Sensitive Fields (PII)** | Field-level encryption | Application-level KMS | ☐ |
| **RFID Tag Data** | No encryption (EPC only key) | Backend database encrypted | ☐ |

### 8.1.4 Network Security

| Control | Implementation | Configuration | Status |
|---------|----------------|---------------|--------|
| **Firewall** | Sophos XG / Fortinet | Allow only required ports | ☐ |
| **IDS/IPS** | Integrated in UTM | Block known attack signatures | ☐ |
| **VPN** | IPSec / SSL VPN | For remote access only | ☐ |
| **VLAN Segmentation** | Management / Production / Guest | Isolate network segments | ☐ |
| **DMZ** | Separate zone for web server | Protect internal network | ☐ |
| **DDoS Protection** | Cloud-based (Cloudflare / AWS Shield) | Auto-mitigation | ☐ |

### 8.1.5 Application Security (OWASP Top 10 Mitigation)

| Vulnerability | Mitigation Strategy | Implementation | Status |
|---------------|---------------------|----------------|--------|
| **Injection (SQL/NoSQL)** | Parameterized queries, Input validation | Mongoose ODM, FastAPI Pydantic | ☐ |
| **Broken Authentication** | Secure session management, MFA | JWT with short expiry, Redis session | ☐ |
| **Sensitive Data Exposure** | Encryption, HTTPS only | TLS 1.3, Field encryption | ☐ |
| **XML External Entities** | Disable XML external entity processing | N/A (JSON API only) | ☐ |
| **Broken Access Control** | Enforce authorization on every request | Middleware authorization check | ☐ |
| **Security Misconfiguration** | Secure default configs, Regular patches | Infrastructure as Code | ☐ |
| **Cross-Site Scripting (XSS)** | Output encoding, Content Security Policy | React auto-escaping, CSP header | ☐ |
| **Insecure Deserialization** | Validate deserialized data | Input validation with Pydantic | ☐ |
| **Using Components with Known Vulnerabilities** | Regular dependency scanning | Dependabot / Snyk | ☐ |
| **Insufficient Logging & Monitoring** | Comprehensive audit trail | Application logging + SIEM | ☐ |

### 8.1.6 Security Testing & Audit

| Test Type | Frequency | Tool / Method | Responsible | Status |
|-----------|-----------|---------------|-------------|--------|
| **Vulnerability Scan** | Monthly | OWASP ZAP / Nessus | IT Security | ☐ |
| **Penetration Test** | Annually | External pentester | IT Security + Vendor | ☐ |
| **Code Security Review** | Per release | Snyk / SonarQube | Developer | ☐ |
| **Security Audit** | Annually | Internal audit team | Internal Audit | ☐ |
| **Compliance Audit** | As required | External auditor | Finance + IT | ☐ |

## 8.2 Compliance & Regulatory Requirements

### 8.2.1 Indonesia Tax Compliance

| Requirement | Implementation | Responsible | Status |
|-------------|----------------|-------------|--------|
| **E-Faktur Integration** | Export format to e-Faktur desktop app | Finance | ☐ |
| **E-Bupot (PPh 23/26)** | Export format to e-Bupot app | Finance | ☐ |
| **E-SPT (Monthly/Annual)** | Data export for SPT preparation | Finance | ☐ |
| **Audit Trail (Coretax Ready)** | Complete transaction history, cannot delete | System (built-in) | ☐ |
| **PSAK Compliance** | Indonesian accounting standard | Finance | ☐ |

### 8.2.2 Data Privacy & Protection (GDPR-Like Compliance)

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| **Data Subject Rights** | Customer can request their data | ☐ |
| **Right to be Forgotten** | Delete customer data on request (with legal retention check) | ☐ |
| **Data Portability** | Export customer data in machine-readable format | ☐ |
| **Consent Management** | Explicit consent for data collection | ☐ |
| **Data Breach Notification** | Notify affected parties within 72 hours | ☐ |
| **Data Retention Policy** | Auto-delete data after retention period | ☐ |
| **Privacy Policy** | Clear privacy policy published | ☐ |

### 8.2.3 Audit Trail Requirements ⚡⚡

**Critical Requirement: Complete Audit Trail untuk Tax Compliance**

**What to Log:**

| Event Type | Data to Log | Retention | Status |
|------------|-------------|-----------|--------|
| **User Login/Logout** | User, timestamp, IP address, device | 5 years | ☐ |
| **Data Modification** | User, table, record ID, old value, new value, timestamp, reason | 7 years | ☐ |
| **Transaction** | Full transaction detail, status changes | 7 years | ☐ |
| **Approval** | Approver, approved item, amount, timestamp | 7 years | ☐ |
| **Data Deletion** | User, deleted record (soft delete), timestamp, reason | 7 years | ☐ |
| **Failed Login** | Username attempted, IP, timestamp | 1 year | ☐ |
| **Security Events** | Event type, source IP, timestamp, action taken | 5 years | ☐ |
| **System Configuration Change** | Admin, config changed, old/new value, timestamp | 5 years | ☐ |

**Audit Trail Integrity:**
- ✅ **Immutable:** Cannot modify or delete audit logs (append-only)
- ✅ **Tamper-proof:** Cryptographic hash to detect tampering
- ✅ **Searchable:** Full-text search capability
- ✅ **Exportable:** Export for external audit

### 8.2.4 Internal Control & Segregation of Duties (SoD)

**Key SoD Rules:**

| Rule | Description | System Enforcement | Status |
|------|-------------|-------------------|--------|
| **Create ≠ Approve** | User yang create PO tidak boleh approve PO sendiri | System check | ☐ |
| **Initiate ≠ Authorize** | User yang initiate payment tidak boleh authorize payment sendiri | System check | ☐ |
| **Record ≠ Reconcile** | User yang record transaction tidak boleh reconcile sendiri | Manual control | ☐ |
| **Custody ≠ Record** | Warehouse yang custody stock tidak boleh adjust stock tanpa approval | Approval required | ☐ |

**Conflicting Roles (Cannot be assigned to same user):**

| Role A | Role B | Risk if Combined | System Enforcement | Status |
|--------|--------|------------------|-------------------|--------|
| Sales | Finance | Fraud risk (create fake invoice) | Prevent role assignment | ☐ |
| Purchasing | Warehouse | Collusion risk (fake receipt) | Prevent role assignment | ☐ |
| Warehouse | Finance | Stock manipulation | Manual control + audit | ☐ |

## 8.3 Data Governance

### 8.3.1 Data Classification

| Classification | Definition | Examples | Access Control | Encryption | Status |
|----------------|------------|----------|----------------|------------|--------|
| **Public** | Can be shared publicly | Product catalog, Company info | Anyone | No | ☐ |
| **Internal** | For internal use only | Employee list, SOP | Authenticated users | No | ☐ |
| **Confidential** | Sensitive business data | Financial data, Customer data | Role-based | Yes (in transit) | ☐ |
| **Restricted** | Highly sensitive | Bank account, Passwords | Need-to-know only | Yes (at rest + transit) | ☐ |

### 8.3.2 Data Quality Metrics (KPIs)

| Metric | Target | Measurement | Frequency | Owner | Status |
|--------|--------|-------------|-----------|-------|--------|
| **Completeness** | ≥ 98% | % of mandatory fields filled | Monthly | Data steward | ☐ |
| **Accuracy** | ≥ 95% | % of data validated as correct | Quarterly | Data steward | ☐ |
| **Consistency** | ≥ 99% | % of data consistent across systems | Monthly | Data steward | ☐ |
| **Timeliness** | ≤ 24 hours | Max delay for data update | Daily | Data steward | ☐ |
| **Duplication** | ≤ 1% | % of duplicate records | Monthly | Data steward | ☐ |

---

# DOMAIN 9 — Organization & Change Management ⚡

> **Assessment Goal:** Ensure organizational readiness untuk adopt new ERP system dan minimize resistance to change.

## 9.1 Change Readiness Assessment

### 9.1.1 Organization Maturity Level

**Rate current maturity (1-5 scale):**

| Dimension | Current Score | Description | Gap to Close | Priority | Status |
|-----------|---------------|-------------|--------------|----------|--------|
| **Process Maturity** | __/5 | 1=Ad-hoc, 5=Optimized | | High | ☐ |
| **Technology Adoption** | __/5 | 1=Manual, 5=Digital-first | | High | ☐ |
| **Change History** | __/5 | 1=Resistant, 5=Embrace change | | Critical | ☐ |
| **Leadership Support** | __/5 | 1=Weak, 5=Strong champion | | Critical | ☐ |
| **User Tech Literacy** | __/5 | 1=Low, 5=High | | High | ☐ |
| **Data Quality Culture** | __/5 | 1=Poor, 5=Excellence | | Medium | ☐ |
| **Communication** | __/5 | 1=Siloed, 5=Transparent | | Medium | ☐ |

**Interpretation:**
- 0-14: **High Risk** — Extensive change management required, slow adoption expected
- 15-24: **Medium Risk** — Moderate change management, average adoption
- 25-35: **Low Risk** — Minimal resistance, fast adoption

### 9.1.2 Stakeholder Analysis Matrix ⚡

**Map All Key Stakeholders:**

| Stakeholder | Role | Influence | Impact on Them | Support Level | Engagement Strategy | Status |
|-------------|------|-----------|----------------|---------------|---------------------|--------|
| **CEO/Owner** | Decision maker | Very High | Medium | ☐ Champion ☐ Supporter ☐ Neutral ☐ Resistant | Weekly briefing | ☐ |
| **Finance Director** | Budget owner | High | High | ☐ Champion ☐ Supporter ☐ Neutral ☐ Resistant | Monthly steering | ☐ |
| **Sales Director** | Process owner | High | High | ☐ Champion ☐ Supporter ☐ Neutral ☐ Resistant | Weekly WG meeting | ☐ |
| **Warehouse Manager** | End user leader | Medium | Very High | ☐ Champion ☐ Supporter ☐ Neutral ☐ Resistant | Daily support | ☐ |
| **IT Manager** | Technical owner | High | Medium | ☐ Champion ☐ Supporter ☐ Neutral ☐ Resistant | Daily support | ☐ |
| **Warehouse Staff** | End users | Low | Very High | ☐ Champion ☐ Supporter ☐ Neutral ☐ Resistant | Training + incentive | ☐ |
| **Sales Team** | End users | Medium | High | ☐ Champion ☐ Supporter ☐ Neutral ☐ Resistant | Training + incentive | ☐ |
| **Finance Team** | End users | Medium | High | ☐ Champion ☐ Supporter ☐ Neutral ☐ Resistant | Training | ☐ |

**Power-Interest Grid:**

```
High Power
│
│  Manage Closely          Keep Satisfied
│  (Finance Dir,           (CEO, Board)
│   Sales Dir)
│
│  Keep Informed           Monitor
│  (Team Leads)            (Staff)
│
└────────────────────────────────────── High Interest
   Low Interest
```

### 9.1.3 Change Impact Assessment

**Impact per Department:**

| Department | Current Process | New Process | Change Level | Training Need | Resistance Risk | Status |
|------------|-----------------|-------------|--------------|---------------|-----------------|--------|
| **Warehouse** | Manual/Excel | ERP + RFID | Very High | Extensive | High | ☐ |
| **Sales** | Manual/WhatsApp | ERP + Mobile app | High | Moderate | Medium | ☐ |
| **Finance** | Accurate/Excel | Integrated ERP | High | Moderate | Medium | ☐ |
| **Purchasing** | Email/Excel | ERP workflow | High | Moderate | Low | ☐ |
| **Production** | Manual log | ERP + IoT | High | Moderate | Medium | ☐ |
| **Management** | Manual report | Dashboard | Medium | Low | Low | ☐ |

**Change Level Scale:**
- **Low:** Minor adjustment, similar process
- **Medium:** Moderate change, new tools
- **High:** Significant change, new workflow
- **Very High:** Complete transformation, new technology

## 9.2 Change Management Strategy

### 9.2.1 Change Management Framework

**ADKAR Model Implementation:**

| Stage | Objective | Activities | Success Criteria | Owner | Status |
|-------|-----------|------------|------------------|-------|--------|
| **Awareness** | Understand why change | Town hall, Email campaign, Poster | ≥80% aware of project | Comm Lead | ☐ |
| **Desire** | Want to support change | Benefit communication, Leadership endorsement | ≥70% positive attitude | HR + Mgmt | ☐ |
| **Knowledge** | Know how to change | Training, Manual, Job aid | ≥90% pass training | Training Lead | ☐ |
| **Ability** | Able to implement | Hands-on practice, Support | ≥80% proficiency | Support Team | ☐ |
| **Reinforcement** | Sustain the change | Reward, Feedback, Continuous improvement | ≥85% adoption after 3 months | Mgmt | ☐ |

### 9.2.2 Communication Plan ⚡

**Communication Matrix:**

| Audience | Message | Channel | Frequency | Owner | Status |
|----------|---------|---------|-----------|-------|--------|
| **All Staff** | Project kick-off | Town hall meeting | Once | CEO | ☐ |
| **All Staff** | Project progress update | Email newsletter | Bi-weekly | Project Manager | ☐ |
| **All Staff** | Go-live announcement | Email + Poster | D-30, D-7, D-1 | Project Manager | ☐ |
| **Department Heads** | Detailed project plan | Steering committee meeting | Monthly | Project Director | ☐ |
| **End Users** | Training schedule | Email + WhatsApp group | 2 weeks before training | Training Lead | ☐ |
| **End Users** | Tips & tricks | Weekly tip via email | Weekly (first 3 months) | Super User | ☐ |
| **IT Team** | Technical updates | Slack channel | As needed | IT Lead | ☐ |
| **Management** | Status report | Email + Dashboard | Weekly | Project Manager | ☐ |

**Key Messages:**

1. **Why Change:** "Current system limits our growth. ERP will enable us to scale to 3x revenue."
2. **What's In It For Me (WIIFM):**
   - Warehouse: "No more manual counting for hours. RFID = 10x faster."
   - Sales: "Real-time stock visibility. No more overselling."
   - Finance: "Automated journal. Close books in 2 days instead of 10."
3. **Support Available:** "We have dedicated support team 24/7 during first month."

### 9.2.3 Resistance Management

**Anticipated Resistance & Mitigation:**

| Resistance Type | Source | Reason | Mitigation Strategy | Owner | Status |
|-----------------|--------|--------|---------------------|-------|--------|
| **"System terlalu rumit"** | Warehouse staff | Low tech literacy | Simplified UI, extensive training, job aid | Training Lead | ☐ |
| **"Lebih cepat cara lama"** | Senior staff | Comfort with old way | Show time savings with demo, early wins | Change Champion | ☐ |
| **"Takut error data"** | Finance team | Fear of mistake | Parallel run, validation checkpoints | Finance Lead | ☐ |
| **"Pekerjaan bertambah"** | All users | Perceived extra work | Show long-term benefit, automation gains | Management | ☐ |
| **"Takut kehilangan pekerjaan"** | Warehouse staff | Job security fear | Reassurance, reskilling program | HR + CEO | ☐ |
| **"Budget terlalu besar"** | Management | Cost concern | ROI analysis, phased investment | Finance Director | ☐ |

**Escalation Path:**
```
Level 1: Direct supervisor (handle day-to-day resistance)
↓
Level 2: Change champion (persistent resistance)
↓
Level 3: Steering committee (organizational resistance)
↓
Level 4: CEO (critical blockers)
```

## 9.3 Super User Program

### 9.3.1 Super User Identification

**Super User Criteria:**

- ✅ Respected by peers (informal leader)
- ✅ Tech-savvy (quick learner)
- ✅ Positive attitude towards change
- ✅ Good communicator
- ✅ Available for training & support (not overly busy)
- ✅ Willing to be change champion

**Super User per Department:**

| Department | Super User Name | Role | Responsibility | Training Hours | Status |
|------------|-----------------|------|----------------|----------------|--------|
| Warehouse 1 | [Name] | Warehouse Supervisor | Train & support 10 staff | 40 hours | ☐ |
| Warehouse 2 | [Name] | Warehouse Supervisor | Train & support 8 staff | 40 hours | ☐ |
| Sales | [Name] | Senior Sales | Train & support 5 sales | 24 hours | ☐ |
| Finance | [Name] | Finance Supervisor | Train & support 4 staff | 24 hours | ☐ |
| Purchasing | [Name] | Senior Buyer | Train & support 3 staff | 16 hours | ☐ |
| Production | [Name] | Production Supervisor | Train & support 6 staff | 24 hours | ☐ |
| IT | [Name] | IT Staff | Technical support | 40 hours | ☐ |

### 9.3.2 Super User Program Structure

**Phase 1: Train the Trainer (2 weeks before general training)**
- Intensive hands-on training
- System admin capabilities
- Troubleshooting skills
- Teaching methodology

**Phase 2: General User Training (with Super User as co-trainer)**
- Super user assist trainer
- Super user demonstrate to peers
- Build credibility

**Phase 3: Go-Live Support (D-7 to D+30)**
- Super user provide floor support
- Escalate issues to IT
- Collect feedback

**Phase 4: Continuous Improvement (D+30 onwards)**
- Super user gather improvement ideas
- Conduct refresher training
- Champion best practices

**Super User Incentive:**
- Certificate of completion
- Bonus/incentive (e.g., Rp 2-5 juta)
- Recognition in company meeting
- Career development opportunity

---

# DOMAIN 10 — Vendor Evaluation & Selection ⚡

> **Assessment Goal:** Select right ERP vendor/implementation partner based on objective criteria dan thorough due diligence.

## 10.1 Vendor Selection Criteria

### 10.1.1 RFP (Request for Proposal) Criteria Matrix

**Weighted Scoring Model:**

| Criteria | Weight | Max Score | Description | Status |
|----------|--------|-----------|-------------|--------|
| **Functional Fit** | 30% | 30 | How well system meets requirements | ☐ |
| **Technical Architecture** | 20% | 20 | Technology stack, scalability, integration | ☐ |
| **Total Cost of Ownership (TCO)** | 15% | 15 | 5-year total cost | ☐ |
| **Vendor Reputation & Stability** | 10% | 10 | Track record, financial health, references | ☐ |
| **Implementation Methodology** | 10% | 10 | Project approach, timeline, risk management | ☐ |
| **Support & Maintenance** | 10% | 10 | SLA, response time, support quality | ☐ |
| **Industry Experience** | 5% | 5 | Textile/distribution industry experience | ☐ |
| **Total** | 100% | 100 | | ☐ |

**Minimum Qualifying Score:** 70/100

### 10.1.2 Detailed Scoring Rubric

**Functional Fit (30 points):**

| Feature Category | Weight | Vendor A Score | Vendor B Score | Vendor C Score | Status |
|------------------|--------|----------------|----------------|----------------|--------|
| **Core ERP (Sales, Purchase, Inventory)** | 40% (12 pts) | __ / 12 | __ / 12 | __ / 12 | ☐ |
| **Warehouse Management & RFID** | 30% (9 pts) | __ / 9 | __ / 9 | __ / 9 | ☐ |
| **Financial & Accounting** | 20% (6 pts) | __ / 6 | __ / 6 | __ / 6 | ☐ |
| **Production Management** | 10% (3 pts) | __ / 3 | __ / 3 | __ / 3 | ☐ |
| **Subtotal** | 100% (30 pts) | __ / 30 | __ / 30 | __ / 30 | ☐ |

**Technical Architecture (20 points):**

| Criteria | Weight | Vendor A | Vendor B | Vendor C | Status |
|----------|--------|----------|----------|----------|--------|
| **Modern Tech Stack** | 25% (5 pts) | __ / 5 | __ / 5 | __ / 5 | ☐ |
| **Cloud-Ready** | 20% (4 pts) | __ / 4 | __ / 4 | __ / 4 | ☐ |
| **API & Integration** | 20% (4 pts) | __ / 4 | __ / 4 | __ / 4 | ☐ |
| **Mobile Support** | 15% (3 pts) | __ / 3 | __ / 3 | __ / 3 | ☐ |
| **Scalability** | 10% (2 pts) | __ / 2 | __ / 2 | __ / 2 | ☐ |
| **Security** | 10% (2 pts) | __ / 2 | __ / 2 | __ / 2 | ☐ |
| **Subtotal** | 100% (20 pts) | __ / 20 | __ / 20 | __ / 20 | ☐ |

### 10.1.3 Vendor Comparison Matrix

| Vendor | Total Score | Functional | Technical | TCO (5yr) | Implementation Time | Support SLA | Recommendation | Status |
|--------|-------------|-----------|-----------|-----------|---------------------|-------------|----------------|--------|
| **Vendor A** | __ / 100 | __ / 30 | __ / 20 | __ / 15 | __ weeks | __ / 10 | ☐ Shortlist | ☐ |
| **Vendor B** | __ / 100 | __ / 30 | __ / 20 | __ / 15 | __ weeks | __ / 10 | ☐ Shortlist | ☐ |
| **Vendor C** | __ / 100 | __ / 30 | __ / 20 | __ / 15 | __ weeks | __ / 10 | ☐ Shortlist | ☐ |

### 10.1.4 Reference Check

**For Shortlisted Vendors, Check at Least 3 References:**

| Reference | Industry | Company Size | Implementation Date | Success? | Key Learning | Contact | Status |
|-----------|----------|--------------|---------------------|----------|--------------|---------|--------|
| Reference 1 | | | | ☐ Yes ☐ No | | | ☐ |
| Reference 2 | | | | ☐ Yes ☐ No | | | ☐ |
| Reference 3 | | | | ☐ Yes ☐ No | | | ☐ |

**Questions to Ask References:**
1. How smooth was the implementation?
2. Did vendor meet timeline & budget?
3. Any major issues during/after go-live?
4. How is post-implementation support?
5. Would you choose this vendor again?
6. Any hidden costs?

## 10.2 Service Level Agreement (SLA) Requirements

### 10.2.1 Support SLA Template

| Support Tier | Description | Response Time | Resolution Time | Availability | Status |
|--------------|-------------|---------------|-----------------|--------------|--------|
| **P1 - Critical** | System down, No workaround | ≤ 1 hour | ≤ 4 hours | 24/7 | ☐ |
| **P2 - High** | Major function not working, Workaround available | ≤ 4 hours | ≤ 1 business day | Business hours | ☐ |
| **P3 - Medium** | Minor issue, No business impact | ≤ 8 hours | ≤ 3 business days | Business hours | ☐ |
| **P4 - Low** | Question, Enhancement request | ≤ 24 hours | As scheduled | Business hours | ☐ |

**Support Channels:**
- Phone: +62-xxx-xxxx-xxxx
- Email: support@vendor.com
- Ticketing portal: portal.vendor.com
- Remote access: For troubleshooting

**Penalty for SLA Breach:**
- Breach P1 SLA → ___% monthly fee credit
- Breach P2 SLA 3x in a month → ___% credit
- Consistent breach → Termination clause

### 10.2.2 Maintenance SLA

| Maintenance Type | Frequency | Duration | Advance Notice | Status |
|------------------|-----------|----------|----------------|--------|
| **Scheduled Maintenance** | Monthly | Max 4 hours | 7 days | ☐ |
| **Emergency Patch** | As needed | Max 2 hours | 24 hours | ☐ |
| **Major Upgrade** | Annually | Max 8 hours | 30 days | ☐ |

**Maintenance Window:** Sunday 00:00-06:00 WIB

## 10.3 Contract Negotiation Points

### 10.3.1 Key Contract Terms

| Term | PT. KN Requirement | Negotiable? | Status |
|------|-------------------|-------------|--------|
| **License Type** | Perpetual preferred / Annual subscription OK | ☐ Yes | ☐ |
| **User License** | Concurrent user (recommended) vs Named user | ☐ Yes | ☐ |
| **Customization** | Included in fixed price vs Separately billed | ☐ Yes | ☐ |
| **Training** | X hours included in package | ☐ Yes | ☐ |
| **Go-Live Support** | 30 days on-site support included | ☐ Yes | ☐ |
| **Source Code Escrow** | Source code access if vendor bankrupt | ☐ Yes | ☐ |
| **Data Ownership** | 100% data owned by PT. KN | ☐ No (must have) | ☐ |
| **Payment Terms** | 30% down, 40% UAT, 30% Go-live | ☐ Yes | ☐ |
| **Warranty Period** | 12 months post go-live | ☐ Yes | ☐ |
| **Termination Clause** | Mutual termination with 90 days notice | ☐ Yes | ☐ |

### 10.3.2 Total Cost of Ownership (TCO) Calculation Template

**5-Year TCO Breakdown:**

| Cost Component | Year 1 | Year 2 | Year 3 | Year 4 | Year 5 | Total (5 years) | Status |
|----------------|--------|--------|--------|--------|--------|-----------------|--------|
| **Software License** | Rp ___ | — | — | — | — | Rp ___ | ☐ |
| **Implementation** | Rp ___ | — | — | — | — | Rp ___ | ☐ |
| **Customization** | Rp ___ | Rp ___ | — | — | — | Rp ___ | ☐ |
| **Training** | Rp ___ | Rp ___ | — | — | — | Rp ___ | ☐ |
| **Infrastructure** | Rp ___ | Rp ___ | Rp ___ | Rp ___ | Rp ___ | Rp ___ | ☐ |
| **Annual Maintenance** | — | Rp ___ | Rp ___ | Rp ___ | Rp ___ | Rp ___ | ☐ |
| **Support Fee** | Rp ___ | Rp ___ | Rp ___ | Rp ___ | Rp ___ | Rp ___ | ☐ |
| **Upgrade** | — | — | Rp ___ | — | Rp ___ | Rp ___ | ☐ |
| **Internal IT Cost** | Rp ___ | Rp ___ | Rp ___ | Rp ___ | Rp ___ | Rp ___ | ☐ |
| **Contingency (10%)** | Rp ___ | Rp ___ | Rp ___ | Rp ___ | Rp ___ | Rp ___ | ☐ |
| **Total per Year** | Rp ___ | Rp ___ | Rp ___ | Rp ___ | Rp ___ | **Rp ___** | ☐ |

---

# DOMAIN 11 — Financial Planning & ROI Analysis ⚡⚡⚡

> **CRITICAL SECTION untuk Investment Justification**

## 11.1 Detailed Budget Breakdown

### 11.1.1 Initial Investment (Year 1)

**Software & Licensing:**

| Item | Specification | Qty | Unit Price | Total | Status |
|------|---------------|-----|------------|-------|--------|
| **ERP Software License** | Perpetual / Annual subscription | 100 users | Rp _______ | Rp _______ | ☐ |
| **RFID Middleware License** | Perpetual | 5 servers | Rp _______ | Rp _______ | ☐ |
| **Database License** (if applicable) | MongoDB Atlas / Self-hosted | 1 | Rp _______ | Rp _______ | ☐ |
| **Mobile App License** | iOS + Android | 20 devices | Rp _______ | Rp _______ | ☐ |
| **Reporting Tool** (if separate) | Power BI / Tableau | 10 users | Rp _______ | Rp _______ | ☐ |
| **Subtotal Software** | | | | **Rp _______** | ☐ |

**Implementation Services:**

| Item | Man-Days | Rate per Day | Total | Status |
|------|----------|--------------|-------|--------|
| **Project Management** | 60 MD | Rp _______ | Rp _______ | ☐ |
| **Business Analyst** | 40 MD | Rp _______ | Rp _______ | ☐ |
| **System Configuration** | 80 MD | Rp _______ | Rp _______ | ☐ |
| **Customization Development** | 120 MD | Rp _______ | Rp _______ | ☐ |
| **Data Migration** | 40 MD | Rp _______ | Rp _______ | ☐ |
| **Integration Development** | 60 MD | Rp _______ | Rp _______ | ☐ |
| **RFID POC & Setup** | 30 MD | Rp _______ | Rp _______ | ☐ |
| **Testing & QA** | 40 MD | Rp _______ | Rp _______ | ☐ |
| **Training** | 30 MD | Rp _______ | Rp _______ | ☐ |
| **Go-Live Support** | 30 MD | Rp _______ | Rp _______ | ☐ |
| **Subtotal Services** | 530 MD | | **Rp _______** | ☐ |

**Hardware & Infrastructure:**

| Item | Specification | Qty | Unit Price | Total | Status |
|------|---------------|-----|------------|-------|--------|
| **Cloud Infrastructure (Year 1)** | See Domain 7 | 12 months | Rp 36 juta/mo | Rp 432 juta | ☐ |
| **Network Equipment** | Firewall, Switch, WiFi | Lump sum | — | Rp 306 juta | ☐ |
| **RFID Hardware** | | | | | |
| - Handheld reader | Chainway C6 / Zebra RFD40 | 10 units | Rp 15 juta | Rp 150 juta | ☐ |
| - Fixed reader + antenna | Impinj R700 + 4 antenna | 6 sets | Rp 60 juta | Rp 360 juta | ☐ |
| - Tag printer/encoder | Zebra ZT411 RFID | 3 units | Rp 35 juta | Rp 105 juta | ☐ |
| - RFID tags (initial stock) | UHF passive tags | 50,000 pcs | Rp 2,500 | Rp 125 juta | ☐ |
| **Tablets/Devices** | For mobile app | 20 units | Rp 4 juta | Rp 80 juta | ☐ |
| **Printer** | Label & document printer | 5 units | Rp 8 juta | Rp 40 juta | ☐ |
| **Subtotal Hardware** | | | | **Rp 1,598 juta** | ☐ |

**Internal Costs:**

| Item | Description | Amount | Status |
|------|-------------|--------|--------|
| **Internal Project Team** | 2 FTE x 12 months x Rp 15 juta | Rp 360 juta | ☐ |
| **Business Disruption** | Productivity loss during transition | Rp 100 juta | ☐ |
| **Travel & Accommodation** | For training & workshops | Rp 50 juta | ☐ |
| **Change Management** | Communication, incentives | Rp 75 juta | ☐ |
| **Subtotal Internal** | | **Rp 585 juta** | ☐ |

**Contingency:**

| Item | Calculation | Amount | Status |
|------|-------------|--------|--------|
| **Contingency (10%)** | 10% of (Software + Services + Hardware) | Rp _______ | ☐ |

**TOTAL INITIAL INVESTMENT (YEAR 1):**

| Category | Amount | % of Total | Status |
|----------|--------|------------|--------|
| Software & Licensing | Rp _______ | __% | ☐ |
| Implementation Services | Rp _______ | __% | ☐ |
| Hardware & Infrastructure | Rp 1,598 juta | __% | ☐ |
| Internal Costs | Rp 585 juta | __% | ☐ |
| Contingency (10%) | Rp _______ | __% | ☐ |
| **GRAND TOTAL YEAR 1** | **Rp _______ juta** | 100% | ☐ |

*(Estimated range: Rp 3-5 Miliar tergantung vendor & customization level)*

### 11.1.2 Recurring Costs (Annual)

| Cost Item | Year 2 | Year 3 | Year 4 | Year 5 | Status |
|-----------|--------|--------|--------|--------|--------|
| **Software Maintenance (15-20% of license)** | Rp ___ | Rp ___ | Rp ___ | Rp ___ | ☐ |
| **Cloud Infrastructure** | Rp 432 juta | Rp 650 juta | Rp 864 juta | Rp 864 juta | ☐ |
| **Internet & Connectivity** | Rp 120 juta | Rp 120 juta | Rp 120 juta | Rp 120 juta | ☐ |
| **RFID Tags (ongoing)** | Rp 150 juta | Rp 200 juta | Rp 250 juta | Rp 300 juta | ☐ |
| **Support Contract** | Rp ___ | Rp ___ | Rp ___ | Rp ___ | ☐ |
| **Internal IT Team (2 FTE)** | Rp 360 juta | Rp 390 juta | Rp 420 juta | Rp 450 juta | ☐ |
| **Training (refresher)** | Rp 50 juta | Rp 30 juta | Rp 30 juta | Rp 30 juta | ☐ |
| **System Enhancements** | Rp 100 juta | Rp 150 juta | Rp 100 juta | Rp 150 juta | ☐ |
| **Total Annual** | **Rp ___ juta** | **Rp ___ juta** | **Rp ___ juta** | **Rp ___ juta** | ☐ |

## 11.2 Cost-Benefit Analysis ⚡⚡

### 11.2.1 Quantifiable Benefits (Hard Savings)

**From Pain Points Analysis (Domain 2):**

| Benefit Category | Current Monthly Cost | Expected Savings | Annual Savings | Status |
|------------------|---------------------|------------------|----------------|--------|
| **Inventory Accuracy Improvement** | | | | |
| - Reduced stock discrepancy loss | Rp 50 juta | 80% reduction | Rp 480 juta | ☐ |
| - Lower dead stock write-off | Rp 30 juta | 50% reduction | Rp 180 juta | ☐ |
| **Labor Cost Reduction** | | | | |
| - Stock opname efficiency (10x faster) | Rp 40 juta labor | 80% reduction | Rp 384 juta | ☐ |
| - Manual data entry elimination | Rp 25 juta labor | 70% reduction | Rp 210 juta | ☐ |
| - Admin overhead reduction | Rp 20 juta | 50% reduction | Rp 120 juta | ☐ |
| **Error Reduction** | | | | |
| - Picking error & wrong shipment | Rp 15 juta | 90% reduction | Rp 162 juta | ☐ |
| - Invoice error & rework | Rp 10 juta | 80% reduction | Rp 96 juta | ☐ |
| - Purchase order error | Rp 8 juta | 70% reduction | Rp 67 juta | ☐ |
| **Financial Impact** | | | | |
| - Faster collection (DSO reduction) | Rp 200 juta cash | Interest saving 12% | Rp 24 juta | ☐ |
| - Better payable terms | | Cash flow benefit | Rp 30 juta | ☐ |
| **Total Quantifiable Benefits** | | | **Rp 1,753 juta/year** | ☐ |

### 11.2.2 Intangible Benefits (Soft Savings)

| Benefit | Description | Estimated Value | Measurement Method | Status |
|---------|-------------|-----------------|-------------------|--------|
| **Faster Decision Making** | Real-time dashboard vs weekly report | High | Survey + time tracking | ☐ |
| **Better Customer Service** | Accurate stock info, faster delivery | High | Customer satisfaction ↑ | ☐ |
| **Scalability** | Can handle 3x revenue without proportional headcount | Very High | Growth without hiring | ☐ |
| **Compliance** | Tax audit ready, complete audit trail | Medium | Reduced audit risk | ☐ |
| **Employee Satisfaction** | Less manual work, more value-add | Medium | Employee survey | ☐ |
| **Competitive Advantage** | Modern system vs competitors | High | Market positioning | ☐ |

### 11.2.3 ROI Calculation ⚡⚡

**Simple ROI (First 5 Years):**

| Year | Investment | Benefits | Net Cash Flow | Cumulative | Status |
|------|------------|----------|---------------|------------|--------|
| Year 0 | (Rp 4,000 juta) | Rp 0 | (Rp 4,000 juta) | (Rp 4,000 juta) | ☐ |
| Year 1 | (Rp 1,000 juta) | Rp 1,200 juta | Rp 200 juta | (Rp 3,800 juta) | ☐ |
| Year 2 | (Rp 1,100 juta) | Rp 1,750 juta | Rp 650 juta | (Rp 3,150 juta) | ☐ |
| Year 3 | (Rp 1,200 juta) | Rp 2,000 juta | Rp 800 juta | (Rp 2,350 juta) | ☐ |
| Year 4 | (Rp 1,250 juta) | Rp 2,300 juta | Rp 1,050 juta | (Rp 1,300 juta) | ☐ |
| Year 5 | (Rp 1,300 juta) | Rp 2,600 juta | Rp 1,300 juta | **Rp 0** | ☐ |

**Payback Period:** ~**4.5 years**

**ROI % (5 years):** 
```
ROI = (Total Benefits - Total Investment) / Total Investment × 100%
ROI = (Rp 9,850 juta - Rp 8,850 juta) / Rp 8,850 juta × 100%
ROI = **11.3%** over 5 years
```

**NPV (Net Present Value) at 10% Discount Rate:**
```
NPV = Σ (Cash Flow / (1 + r)^t)
NPV = Rp _______ juta
```

**IRR (Internal Rate of Return):**
```
IRR = __.__%
```

*(Note: Adjust angka berdasarkan actual cost & benefit dari assessment)*

### 11.2.4 Sensitivity Analysis

**Best Case Scenario (Benefits 20% higher):**
- Payback Period: **3.5 years**
- ROI: **33%**

**Base Case Scenario (As calculated above):**
- Payback Period: **4.5 years**
- ROI: **11%**

**Worst Case Scenario (Benefits 20% lower, Cost 20% higher):**
- Payback Period: **6+ years**
- ROI: **-10%** (negative in 5 years)

**Break-Even Analysis:**
```
Minimum annual benefit to break even in 5 years = Rp _______ juta/year
```

## 11.3 Budget Approval & Funding Strategy

### 11.3.1 Budget Request Template

**To:** Board of Directors / Owner
**From:** Project Sponsor
**Subject:** ERP & RFID Implementation Investment Approval

**Executive Summary:**
- Total Investment: Rp ____ Miliar (5 years)
- Expected Annual Savings: Rp 1.75 Miliar/year (Year 2+)
- Payback Period: 4.5 years
- Strategic Necessity: Enable 3x revenue growth

**Funding Options:**

| Option | Pros | Cons | Recommendation | Status |
|--------|------|------|----------------|--------|
| **Internal Cash** | No interest cost | Large cash outflow | If cash position strong | ☐ |
| **Bank Loan** | Preserve cash | Interest 10-12% | If need working capital | ☐ |
| **Vendor Financing** | Flexible payment | Higher total cost | For cash flow management | ☐ |
| **Lease** | Lower upfront | No asset ownership | For hardware only | ☐ |

**Recommended Phased Investment:**
- Phase 1 (POC): Rp 200 juta
- Phase 2 (Pilot): Rp 1,500 juta
- Phase 3 (Full rollout): Rp 2,300 juta

This allows stopping after POC if results not satisfactory.

---

*(DOCUMENT CONTINUES TO DOMAIN 12-15...)*

**Current Status: 75% Complete**

Apakah saya lanjutkan ke **Domain 12-15 (Implementation Roadmap, Testing, Training, Go-Live)** untuk melengkapi dokumen secara total?

Atau Anda ingin saya fokuskan detail di bagian tertentu dulu?
