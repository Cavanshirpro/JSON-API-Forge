# Production checklist

- [ ] Python version supported by all dependencies
- [ ] `.env` excluded from Git and public web roots
- [ ] bootstrap key generated randomly
- [ ] JWT secret generated randomly if JWT is enabled
- [ ] production database is PostgreSQL/MySQL rather than SQLite for concurrent traffic
- [ ] database TLS configured where required
- [ ] least-privilege DB user
- [ ] exact CORS origins
- [ ] HTTPS enforced
- [ ] reverse-proxy/body-size/timeouts configured
- [ ] each plugin has its own API key
- [ ] API keys have minimum permissions
- [ ] migration/backup plan exists
- [ ] logs do not contain secrets
- [ ] `/docs` exposure is intentional
- [ ] shared/distributed rate limiting added before multi-worker high-traffic deployment
- [ ] monitoring/alerts added
- [ ] restore-from-backup tested
