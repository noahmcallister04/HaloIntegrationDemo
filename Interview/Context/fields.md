# Halo Ticket Fields Reference

Reference for the fields on a FeatherShark HaloPSA ticket and the allowed values a technician selects when creating a ticket. Use these exact field names and values when generating mock data, building the mock Halo API, and matching tickets.

---

## 1. Ticket Fields

| Field | Description / Notes |
|---|---|
| Ticket ID | Unique ticket number |
| Summary | Short title (often user-written, inconsistent) |
| Client | Customer organization (fire/EMS department) |
| User | End user who reported the issue |
| Type | Top-level category (see §3) |
| Subtype | Category under Type (see §3) |
| Priority | Ticket priority |
| Status | Current ticket status |
| Team | Team the ticket is assigned to |
| Agent | Primary assigned technician |
| Additional Agent | Secondary technician |
| Date Reported | When the ticket was created |
| Last Action Date | When the last action/note was added |
| Resolution Target | Target resolution date/time |
| SLA Time Left | Time remaining before SLA breach |
| SLA Action Date | Date the next SLA action is due |
| Time Taken | Time logged on the ticket |

---

## 2. Fields Set at Ticket Creation

### Impact
| Value | Label |
|---|---|
| 1 | Company |
| 2 | Multiple Users Affected |
| 3 | Single User Affected |

### Urgency
| Value | Label |
|---|---|
| 1 | High |
| 2 | Medium |
| 3 | Low |

---

## 3. Types and Subtypes

| Type | Subtypes |
|---|---|
| Account Administration | Account Information Change, Application Access, Folder Access, G2 Alerting Configuration, Mail Access, New Account, New Application Account, New Distribution Group, New Mailbox, Password Reset, Suspend/Disable Account, User Termination/Leaving |
| Alert | Backup Alerts, CW Control Message, Email Alerts, Huntress Alerts, Ninja Alerts, StatusCake Alerts, UniFi Alerts, Vendor Alerts |
| Backup | Datto SaaS, Datto/Kaseya, Egnyte, Local Device, MSP 360, Slide |
| FeatherShark Software | Code Final, Internal Projects, Live Dash |
| Hardware | Access Point, Airtame, Camera NVR, Desk Phone, Desktop, Docking Station, Door Locks/Bells, Fax Machine, Gateway/Router, Headsets, ID Badge Printer, Laptop, MDT, Monitor, PC Accessory, Printer, Projector, Request, Return, Scanners, Server, Smartphone/iPad/Tablet, Speakers, Switch, TV, Zoom Room |
| Infrastructure | Server Data Move, Server File Share, Server Hardware Failure, Server Replacement, Updates Failed |
| Inquiries | General Knowledge, Software, Technical |
| IT Security Threats | Email Spoofing, File Contains Passwords, Huntress, Malware, Phishing Email, Ransomware, Virus |
| Network | DNS, ISP Outage, Unable to Connect, UniFi Configuration Change, VPN Configuration, WiFi Outage |
| Security | Compromised Account, Compromised Computer, Compromised Email |
| Setup | Computer Setup, MDT Setup, Network Setup, Phone Setup, Printer Setup |
| Standard Applications | Adobe, Browser, CAD Applications, Door Access, Egnyte Desktop, Egnyte Web, Email, Gmail, JumpCloud, LastPass, MS Office, Operating System, Other (Not Listed), Outlook, QuickBooks, RDS, Trustifi, VPN Client, Web App, Zoom |
| Telephony | Coredial, Mobile App, RingCentral, SkySwitch, Yealink RPS |
| Website | DNS Cloudflare, GoDaddy |

---

## 4. Notes for the Similar Resolved Tickets Project

- **Type + Subtype** act as the ticket category. Use them as a structured boost in matching (same Type/Subtype = higher score).
- **Client** is used for the same-client boost.
- **Summary** is the main free-text field for semantic matching.
- **Resolution / notes are not in the field list above.** The project needs closed-ticket resolution text. Confirm which Halo field or action notes hold the fix (e.g. a closing note or resolution field).
- **Priority vs. Impact/Urgency:** confirm whether Halo derives Priority from an Impact × Urgency matrix. If so, mock data should follow that matrix.
- **Values normalized from the original notes. Verify against Halo before relying on exact spelling:**
  - "CW Controll message" → `CW Control Message`
  - "huntress, alerts" → `Huntress Alerts` (assumed one value, not two)
  - "Inquires" → `Inquiries`
  - "ransomeware" → `Ransomware`
  - "user termination\leaving" → `User Termination/Leaving`