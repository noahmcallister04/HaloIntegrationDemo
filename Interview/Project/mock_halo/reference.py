"""Reference values for the mock Halo instance.

Types/subtypes come from Context/fields.md. Clients, people and units are fictional.
"""

TYPES: dict[str, list[str]] = {
    "Account Administration": [
        "Account Information Change", "Application Access", "Folder Access",
        "G2 Alerting Configuration", "Mail Access", "New Account", "New Application Account",
        "New Distribution Group", "New Mailbox", "Password Reset", "Suspend/Disable Account",
        "User Termination/Leaving",
    ],
    "Alert": [
        "Backup Alerts", "CW Control Message", "Email Alerts", "Huntress Alerts", "Ninja Alerts",
        "StatusCake Alerts", "UniFi Alerts", "Vendor Alerts",
    ],
    "Backup": ["Datto SaaS", "Datto/Kaseya", "Egnyte", "Local Device", "MSP 360", "Slide"],
    "FeatherShark Software": ["Code Final", "Internal Projects", "Live Dash"],
    "Hardware": [
        "Access Point", "Airtame", "Camera NVR", "Desk Phone", "Desktop", "Docking Station",
        "Door Locks/Bells", "Fax Machine", "Gateway/Router", "Headsets", "ID Badge Printer",
        "Laptop", "MDT", "Monitor", "PC Accessory", "Printer", "Projector", "Request", "Return",
        "Scanners", "Server", "Smartphone/iPad/Tablet", "Speakers", "Switch", "TV", "Zoom Room",
    ],
    "Infrastructure": [
        "Server Data Move", "Server File Share", "Server Hardware Failure", "Server Replacement",
        "Updates Failed",
    ],
    "Inquiries": ["General Knowledge", "Software", "Technical"],
    "IT Security Threats": [
        "Email Spoofing", "File Contains Passwords", "Huntress", "Malware", "Phishing Email",
        "Ransomware", "Virus",
    ],
    "Network": [
        "DNS", "ISP Outage", "Unable to Connect", "UniFi Configuration Change", "VPN Configuration",
        "WiFi Outage",
    ],
    "Security": ["Compromised Account", "Compromised Computer", "Compromised Email"],
    "Setup": ["Computer Setup", "MDT Setup", "Network Setup", "Phone Setup", "Printer Setup"],
    "Standard Applications": [
        "Adobe", "Browser", "CAD Applications", "Door Access", "Egnyte Desktop", "Egnyte Web",
        "Email", "Gmail", "JumpCloud", "LastPass", "MS Office", "Operating System",
        "Other (Not Listed)", "Outlook", "QuickBooks", "RDS", "Trustifi", "VPN Client", "Web App",
        "Zoom",
    ],
    "Telephony": ["Coredial", "Mobile App", "RingCentral", "SkySwitch", "Yealink RPS"],
    "Website": ["DNS Cloudflare", "GoDaddy"],
}

IMPACTS = {1: "Company", 2: "Multiple Users Affected", 3: "Single User Affected"}
URGENCIES = {1: "High", 2: "Medium", 3: "Low"}

STATUSES = ["New", "In Progress", "Waiting on User", "Closed"]
TEAMS = ["Service Desk", "Field Services", "Network", "Security"]
AGENTS = ["Alex Rivera", "Jordan Pike", "Sam Whitfield", "Taylor Brooks", "Morgan Lee", "Casey Dunn"]

CLIENTS: dict[str, dict] = {
    "Riverside Fire Dept": {
        "domain": "riversidefire.example",
        "sites": ["Station 1", "Station 2", "Station 3", "Station 4", "Station 5", "Admin Office"],
        "units": ["Engine 1", "Engine 4", "Ladder 2", "Medic 3", "Medic 5", "Battalion 1"],
    },
    "Cedar County EMS": {
        "domain": "cedarcountyems.example",
        "sites": ["Station 6", "Station 7", "Station 8", "Admin Office", "Dispatch Center"],
        "units": ["Medic 6", "Medic 7", "Medic 8", "Medic 12", "Supervisor 1"],
    },
    "Lakeview Fire & Rescue": {
        "domain": "lakeviewfire.example",
        "sites": ["Station 9", "Station 10", "Admin Office"],
        "units": ["Engine 9", "Rescue 10", "Medic 9", "Tanker 10"],
    },
    "Pine Ridge Fire District": {
        "domain": "pineridgefire.example",
        "sites": ["Station 11", "Station 12", "Admin Office", "Dispatch Center"],
        "units": ["Engine 11", "Brush 12", "Medic 11", "Squad 12"],
    },
}
