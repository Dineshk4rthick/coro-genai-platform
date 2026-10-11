# Contoso Password and Multi-Factor Authentication Policy

**Policy ID:** IT-SEC-001  
**Effective date:** 1 January 2026  
**Policy owner:** Information Technology & Security

## 1. Purpose and scope

This policy establishes the technical and behavioral requirements for authentication mechanisms across Contoso systems, accounts, and managed services. It is a fictional policy created for testing the Contoso PolicyAssistant project and does not represent a real company's rules.

## 2. Password complexity requirements

All user accounts accessing Contoso systems must utilize strong passwords or passphrases meeting the following minimum standards:
- Minimum length of 14 characters.
- Must include at least one uppercase letter, one lowercase letter, one numeric digit, and one special symbol.
- Must not contain obvious personal details, predictable patterns (e.g., "Contoso2026!"), or previously breached passwords.

Password expiration is set to 90 days for privileged accounts and 180 days for standard accounts. The system restricts reuse of the previous 10 passwords.

## 3. Multi-Factor Authentication (MFA)

Multi-Factor Authentication (MFA) is mandatory for all employees accessing corporate systems, including webmail, VPN, single sign-on (SSO) portals, and cloud infrastructure.

Acceptable second factors include:
- Company-managed authenticator apps (push notification or TOTP code).
- Hardware security keys (FIDO2/WebAuthn).

SMS and voice-call verification are considered deprecated and may only be enabled on an emergency, temporary basis with approval from the IT Service Desk.

## 4. Account credential security

Employees must never disclose their passwords to colleagues, managers, or external parties. IT support staff will never ask for an employee’s password.

Credentials must not be written down, stored in unencrypted text files, or saved in unauthorized personal password managers. Employees are provisioned an enterprise password vault for secure credential storage.

## 5. Account lockout and recovery

User accounts are automatically locked after five consecutive failed login attempts. Account unlock requests require identity verification through the IT Service Desk or the self-service authentication portal.

Shared or generic logins (e.g., `admin`, `shared-team`) are prohibited unless approved as service accounts with restricted access and dedicated logging.

## 6. Responsibilities

Users are responsible for safeguarding their login credentials and promptly reporting unusual MFA prompts. The IT Security team is responsible for configuring authentication gateways, monitoring suspicious login attempts, and enforcing MFA enforcement policies across enterprise directories.

## 7. Questions and exceptions

Questions or credential issues should be directed to the IT Service Desk. Any temporary MFA exemption for travel or hardware loss requires written approval from the Head of IT Security.