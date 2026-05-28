# Batch Flip — Data Classification Document

**Version:** 1.0
**Last Review:** 2026-05-27
**Compliance:** Amazon SP-API Data Protection Policy

---

## 1. Data Categories

### CONFIDENTIAL — Encrypted at Rest (AES-128 Fernet)

| Data | Storage | Encryption | Retention |
|------|---------|-----------|-----------|
| Amazon refresh_token (per seller) | `seller_connections.refresh_token_encrypted` | ✅ Fernet AES-128-CBC | Until seller disconnects |
| SP-API client_secret | `.env` file (not in DB) | ✅ Server env var | Rotated annually |
| SP-API refresh_token (dev) | `.env` file (not in DB) | ✅ Server env var | Rotated annually |
| Supabase service_role_key | `.env` file (not in DB) | ✅ Server env var | N/A |
| ENCRYPTION_KEY | `.env` file (not in DB) | ✅ Server env var | Rotated annually |

### INTERNAL — Not Encrypted, Access Controlled

| Data | Storage | Access | Retention |
|------|---------|--------|-----------|
| User email | Supabase Auth | Auth service only | Until account deletion |
| User password hash | Supabase Auth (bcrypt) | Auth service only | Until account deletion |
| Seller ID | `seller_connections.seller_id` | App + DB | Until disconnection |
| Store name | `seller_connections.store_name` | App + DB | Until disconnection |
| Job configuration | `jobs.*` | User's own jobs only | 18 months max |

### PRODUCT DATA — Amazon Information, Not PII

| Data | Storage | Source | Retention |
|------|---------|--------|-----------|
| Product title, brand, ASIN | `job_items.*` | SP-API + Keepa | 18 months max |
| Buy Box price, BSR, fees | `job_items.*` | SP-API + Keepa | 18 months max |
| Listing restrictions | `job_items.can_sell` | SP-API | 18 months max |
| Monthly sold, reviews, rating | `job_items.*` | Keepa | 18 months max |
| Profit calculations | `job_items.profit/roi/margin` | Calculated | 18 months max |

### AUDIT — Security Logs

| Data | Storage | Retention |
|------|---------|-----------|
| Auth events (login/register) | `audit_logs` | 12 months minimum |
| Amazon data access events | `audit_logs` | 12 months minimum |
| Key rotation events | `audit_logs` | 12 months minimum |
| Error events | `audit_logs` | 12 months minimum |

## 2. Data We Do NOT Collect

| Data | Reason |
|------|--------|
| Amazon buyer PII | We do not use Restricted roles (no Direct-to-Consumer, no Tax Invoicing) |
| Order data | We do not access Orders API |
| Customer emails/addresses | Not accessible with our SP-API roles |
| Payment information | Not accessible |
| Buyer communication | Not accessible |

## 3. Encryption Standards

| Algorithm | Usage | Minimum |
|-----------|-------|---------|
| Fernet (AES-128-CBC) | Refresh tokens at rest | ✅ Meets Amazon AES-128 minimum |
| TLS 1.2+ | All data in transit | ✅ Supabase + SP-API enforce TLS |
| bcrypt | User passwords | ✅ Supabase Auth handles this |

### Prohibited Algorithms
DES, RC4, RSA-PKCSv1.5 (1024-bit), Blowfish, Twofish — none of these are used.

## 4. Key Management

| Key | Rotation | Storage | Access |
|-----|----------|---------|--------|
| ENCRYPTION_KEY | Annual (+ on-demand if compromised) | Server env var | App process only |
| SP-API client_secret | Annual | Server env var | App process only |
| Seller refresh_tokens | On re-authorization | DB (encrypted) | App process only |

### Key Rotation Process
1. Generate new key: `GET /api/v1/admin/generate-key`
2. Set new key as `ENCRYPTION_KEY`, old as `ENCRYPTION_KEY_PREVIOUS`
3. Restart app
4. Run rotation: `POST /api/v1/admin/rotate-encryption-key`
5. Remove `ENCRYPTION_KEY_PREVIOUS` after verification

## 5. Data Flow

```
Seller → Supabase Auth → JWT → FastAPI
                                  ↓
                          SellerConnection (encrypted token)
                                  ↓
                          SP-API (using seller's token)
                                  ↓
                          Product data → job_items (no PII)
                                  ↓
                          Audit log → audit_logs
```

## 6. Access Control

| Role | Access |
|------|--------|
| App process | All data (runtime) |
| DB admin (Supabase dashboard) | All tables (restricted to owner) |
| User (via API) | Own jobs, own seller connections only |
| Public | None — all endpoints require JWT |
