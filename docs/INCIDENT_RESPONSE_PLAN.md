# Batch Flip — Incident Response Plan

**Version:** 1.0
**Last Review:** 2026-05-27
**Next Review:** 2026-11-27 (6 months)
**Approved by:** Alex Montesino, CEO

---

## 1. Purpose

This plan defines procedures for detecting, responding to, and recovering from security incidents involving Amazon Information processed by Batch Flip, in compliance with Amazon's Data Protection Policy.

## 2. Scope

Applies to all systems that process, store, or transmit Amazon Selling Partner API data:
- Batch Flip API (FastAPI backend)
- Supabase PostgreSQL (database)
- Supabase Auth (authentication)
- Amazon SP-API credentials and tokens

## 3. Incident Management Point of Contact (IMPOC)

| Role | Name | Contact |
|------|------|---------|
| IMPOC | Alex Montesino | alexmontesinocastro9@gmail.com |
| Backup | [TBD] | [TBD] |

## 4. Amazon Notification Requirement

**CRITICAL: Notify Amazon within 24 hours of detecting any security incident involving Amazon Information.**

Contact: **security@amazon.com**

Include in notification:
- Date/time of detection
- Description of the incident
- Data potentially affected
- Actions taken to contain and remediate

## 5. Incident Categories

| Severity | Description | Response Time |
|----------|-------------|--------------|
| **Critical** | Data breach of Amazon tokens, PII exposure, unauthorized access to SP-API | Immediate (within 1 hour) |
| **High** | Failed encryption, key compromise, unauthorized admin access | Within 4 hours |
| **Medium** | Repeated failed login attempts, unusual API patterns | Within 24 hours |
| **Low** | Policy violation, missing logs, configuration drift | Within 72 hours |

## 6. Response Phases

### Phase 1: Preparation
- [ ] Maintain this plan, review every 6 months
- [ ] Ensure audit logging is active (audit_logs table)
- [ ] Verify encryption keys are rotated annually
- [ ] Ensure team has access to Supabase dashboard and server logs

### Phase 2: Identification
- Monitor audit_logs for anomalies:
  - Multiple failed logins from same IP
  - Unusual SP-API access patterns
  - Token decryption failures
  - Unauthorized admin endpoint access
- Review logs bi-weekly

### Phase 3: Containment
- **Immediate:** Revoke compromised tokens (`SellerConnection.is_active = False`)
- **Immediate:** Rotate encryption key if key compromise suspected
- **Immediate:** Disable affected user accounts in Supabase
- **Short-term:** Block suspicious IPs

### Phase 4: Eradication
- Identify root cause from audit logs
- Patch vulnerability
- Re-encrypt all tokens with new key if needed
- Verify no unauthorized data exfiltration

### Phase 5: Recovery
- Re-enable services after verification
- Notify affected sellers to re-authorize if tokens were revoked
- Verify all systems operational

### Phase 6: Lessons Learned
- Document incident timeline
- Update this plan with improvements
- Implement additional monitoring if needed

## 7. Contact Information

| Service | Action |
|---------|--------|
| Amazon Security | security@amazon.com (within 24h) |
| Supabase | Dashboard → Support |
| SP-API Developer Support | developer-docs.amazon.com/sp-api |

## 8. Review Schedule

| Date | Reviewer | Status |
|------|----------|--------|
| 2026-05-27 | Alex Montesino | Created |
| 2026-11-27 | | Pending |
| 2027-05-27 | | Pending |
