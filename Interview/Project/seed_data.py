"""Generates realistic, deliberately messy fire/EMS tickets into the mock Halo database.

All clients, people and incidents are fictional. Run directly to (re)seed:
    python seed_data.py
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, timedelta

from mock_halo import db
from mock_halo.reference import AGENTS, CLIENTS, TYPES
from settings import resolve_path

RNG_SEED = 20261005
FIRST_TICKET_ID = 45001
LABELS_PATH = resolve_path("data/seed_labels.json")

TOUGHBOOK = ["toughbook", "Toughbook", "CF-33", "cf33", "tuffbook", "toughbok"]
TOUGHBOOK_ANY = TOUGHBOOK + ["truck laptop", "laptop", "rugged laptop"]
EPCR_DEVICE = ["toughbook", "tablet", "iPad", "CF-33", "truck computer"]
PRINTER = ["printer", "copier", "the copier", "mfp", "priner", "Ricoh", "big printer"]

# Each scenario is one kind of problem. Every summary/detail/resolution inside a scenario is
# interchangeable, so a generated ticket's fix always fits its symptoms.
SCENARIOS: list[dict] = [
    {
        "key": "cad_modem", "count": 20, "type": "Standard Applications", "subtype": "CAD Applications",
        "assets": ["Panasonic CF-33", "Panasonic CF-31"], "device": TOUGHBOOK, "impact": 3, "urgency": 1,
        "summaries": [
            "{dev} wont connect to CAD", "CAD not connecting on {unit} {dev}", "no cad on {unit}",
            "CAD offline in {unit} again", "{unit} not getting calls on the {dev}", "cad keeps disconnecting",
            "CAD server unavailable msg",
        ],
        "details": [
            "The {dev} in {unit} keeps saying CAD server unavailable. We had to run calls off the radio all morning.",
            "CAD shows the red disconnected icon on {unit}'s {dev}. Rebooted it twice, still nothing.",
            "{unit} isn't getting dispatches on the {dev}. Says no network. Other units are fine.",
            "cad keeps dropping in and out on the {dev} when we leave the station. works in the bay but not on the road",
            "Crew says the {dev} lost CAD connection after they came back from the call. Signal icon shows nothing.",
        ],
        "resolutions": [
            "Cradlepoint in {unit} had dropped off LTE. Power-cycled the modem, confirmed signal in NetCloud, CAD client reconnected.",
            "Vehicle modem was on the wrong APN after the carrier update. Re-pushed Cradlepoint config from NetCloud, CAD back online.",
            "Loose antenna lead on the roof antenna in {unit}. Reseated the connectors on the modem, CAD reconnected and test incident received.",
            "Modem SIM was deactivated by the carrier. Swapped in a spare SIM and opened a carrier ticket to reactivate the original. CAD connected.",
        ],
    },
    {
        "key": "cad_vpn", "count": 12, "type": "Standard Applications", "subtype": "VPN Client",
        "assets": ["Panasonic CF-33"], "device": TOUGHBOOK, "impact": 3, "urgency": 1,
        "summaries": [
            "vpn stuck connecting on {dev}", "{dev} says vpn error cant get to cad", "mobility vpn wont connect",
            "VPN issue {unit}", "certificate error on vpn",
        ],
        "details": [
            "Mobility VPN client is stuck on 'connecting' on the {dev} in {unit} so CAD and records won't load.",
            "Getting a certificate error when the {dev} tries to connect to VPN. CAD just spins.",
            "The vpn icon is yellow and CAD wont log in. {unit} {dev}",
        ],
        "resolutions": [
            "Mobility VPN client stuck in connecting state. Cleared the client cache and re-registered the device; tunnel came up and CAD connected.",
            "Device certificate on the {dev} had expired. Renewed cert through Intune, forced a sync, VPN tunnel up and CAD working.",
            "VPN client service was set to disabled after an update. Set the service back to automatic, rebooted, VPN connected.",
        ],
    },
    {
        "key": "cad_crash", "count": 12, "type": "Standard Applications", "subtype": "CAD Applications",
        "assets": ["Panasonic CF-33", "Panasonic CF-31"], "device": TOUGHBOOK, "impact": 3, "urgency": 1,
        "summaries": [
            "CAD crashes when opening", "cad app closes by itself", "CAD wont open after update",
            "mobile cad error on startup", "cad crashing on {dev}",
        ],
        "details": [
            "Every time we open the CAD client on the {dev} it closes right away. Started after it did updates last night.",
            "CAD mobile gives an 'unhandled exception' error on startup and then closes.",
            "{unit} {dev} - CAD opens for a second then crashes. Tried restarting.",
        ],
        "resolutions": [
            "CAD client crashing after Windows cumulative update. Ran the CAD client repair and cleared the local CAD cache folder in AppData. Launches clean now.",
            "Reinstalled CAD mobile client 5.2 and re-entered the unit ID. Tested with dispatch, working.",
            "Corrupt CAD client config file after update. Restored default config from the deployment share and re-entered unit settings.",
        ],
    },
    {
        "key": "cad_unit_id", "count": 8, "type": "Standard Applications", "subtype": "CAD Applications",
        "assets": ["Panasonic CF-33"], "device": TOUGHBOOK, "impact": 3, "urgency": 2,
        "summaries": [
            "{dev} logged in as wrong unit", "cad showing wrong unit number", "getting other trucks calls on cad",
            "{unit} showing as {unit2} in cad",
        ],
        "details": [
            "We swapped {dev}s between rigs and now CAD shows us as the wrong unit. Getting {unit2}'s calls.",
            "CAD has us as {unit2} but we're {unit}. Dispatch says they can't see our status.",
        ],
        "resolutions": [
            "Unit ID was still set from the previous rig after the {dev} swap. Updated unit assignment in CAD client settings and had dispatch verify status.",
            "Updated the CAD unit profile on the {dev} to {unit}, logged the crew back in, dispatch confirmed status changes.",
        ],
    },
    {
        "key": "vehicle_dock", "count": 12, "type": "Hardware", "subtype": "Docking Station",
        "assets": ["Havis DS-PAN-1100", "Gamber-Johnson CF-33 Dock"], "device": TOUGHBOOK_ANY, "impact": 3, "urgency": 2,
        "summaries": [
            "{dev} not charging in truck", "dock in {unit} not working", "{dev} wont charge in the mount",
            "{dev} dies on calls", "truck dock broken",
        ],
        "details": [
            "The {dev} in {unit} isn't charging when it's in the dock. Battery died halfway through a call.",
            "Dock in {unit} doesn't seem to have power. No lights. {dev} only charges on the wall charger.",
            "{dev} loses power and the keyboard when it's docked in {unit}.",
        ],
        "resolutions": [
            "Dock pins were dirty and one was bent. Cleaned the dock contacts and reseated the {dev}; charging and passthrough working.",
            "Blown 10A inline fuse on the vehicle dock power lead. Replaced the fuse, dock charging again.",
            "Dock power cable worn through at the mount. Replaced the cable, confirmed charging and USB passthrough.",
        ],
    },
    {
        "key": "toughbook_touch", "count": 8, "type": "Hardware", "subtype": "Laptop",
        "assets": ["Panasonic CF-33", "Panasonic CF-31"], "device": TOUGHBOOK_ANY, "impact": 3, "urgency": 2,
        "summaries": [
            "{dev} touchscreen not working", "screen not responding to touch", "touch screen jumping around",
            "{dev} screen wont register taps",
        ],
        "details": [
            "Touchscreen on the {dev} doesn't respond, have to use the trackpad for everything.",
            "The touch screen on the {dev} in {unit} is registering taps in the wrong spot.",
        ],
        "resolutions": [
            "Recalibrated the touchscreen in the Panasonic utility and updated touch firmware. Responding normally.",
            "Digitizer failure. Swapped the {dev} with a spare from stock and sent the unit for depot repair.",
            "Screen protector was bubbled and causing ghost touches. Replaced protector and recalibrated.",
        ],
    },
    {
        "key": "toughbook_power", "count": 8, "type": "Hardware", "subtype": "Laptop",
        "assets": ["Panasonic CF-33", "Panasonic CF-31"], "device": TOUGHBOOK_ANY, "impact": 3, "urgency": 2,
        "summaries": [
            "{dev} wont turn on", "{dev} battery dies fast", "{dev} battery swollen", "{dev} dead",
        ],
        "details": [
            "{dev} won't power on even plugged in. Tried a different charger.",
            "Battery on the {dev} only lasts about an hour now.",
            "The {dev} battery looks swollen and the cover won't close.",
        ],
        "resolutions": [
            "Battery health at 41%. Replaced the battery from stock, RMA'd the old one with Panasonic.",
            "Drained residual power (battery out, held power 30s), reseated battery. Boots normally.",
            "Battery swollen. Pulled the unit from service, replaced battery, disposed of the old one per policy.",
        ],
    },
    {
        "key": "epcr_sync", "count": 18, "type": "Standard Applications", "subtype": "Web App",
        "device": EPCR_DEVICE, "impact": 3, "urgency": 1,
        "summaries": [
            "epcr wont sync", "patient reports stuck uploading", "charting software not syncing",
            "PCR sync error", "reports not going to hospital", "ePCR says pending upload",
        ],
        "details": [
            "ePCR on the {dev} has {k} reports stuck in pending. They won't upload to the server.",
            "Charting software says sync failed every time. Crew can't close out their reports.",
            "Hospital says they never got our patient report from this morning. ePCR shows it as pending.",
        ],
        "resolutions": [
            "ePCR client auth token expired. Signed out and back in, forced a manual sync, {k} pending reports uploaded.",
            "Local ePCR database was full. Cleared already-synced records from the local cache, sync completed.",
            "Device clock was 20 minutes off which broke auth. Fixed time sync (w32tm /resync), ePCR synced right away.",
        ],
    },
    {
        "key": "epcr_print", "count": 8, "type": "Standard Applications", "subtype": "Web App",
        "device": EPCR_DEVICE, "impact": 3, "urgency": 2,
        "summaries": [
            "cant print patient report", "epcr printing to wrong printer", "patient report wont print",
        ],
        "details": [
            "When we try to print the patient report for the hospital nothing happens.",
            "ePCR keeps sending the report to the admin office printer instead of the station one.",
        ],
        "resolutions": [
            "Default printer was reset after a Windows update. Set the station printer as default in Windows and in ePCR print settings.",
            "ePCR prints through the browser PDF viewer and the popup blocker was stopping it. Allowed popups for the ePCR site.",
        ],
    },
    {
        "key": "printer_driver", "count": 16, "type": "Hardware", "subtype": "Printer",
        "assets": ["Ricoh IM C3000", "HP LaserJet M404", "Brother MFC-L8900"], "device": PRINTER, "impact": 3, "urgency": 2,
        "summaries": [
            "cant print", "{dev} wont print", "printing stuck in queue", "print jobs disappear",
            "{dev} says offline on my pc", "nothing printing from my computer",
        ],
        "details": [
            "I send stuff to the {dev} and nothing comes out. Queue says error - printing.",
            "Can't print from my computer to the {dev}. Other people can print fine.",
            "jobs get stuck in the print queue and wont clear",
        ],
        "resolutions": [
            "Cleared the print spooler and deleted stuck jobs, reinstalled the Ricoh PCL6 driver. Test page printed.",
            "Print spooler service hung. Restarted the spooler, removed and re-added the printer from the print server.",
            "Driver had been swapped to the generic Microsoft one by Windows update. Installed the correct PCL6 driver, printing normally.",
        ],
    },
    {
        "key": "printer_offline", "count": 10, "type": "Hardware", "subtype": "Printer",
        "assets": ["Ricoh IM C3000", "HP LaserJet M404"], "device": PRINTER, "impact": 2, "urgency": 2,
        "summaries": [
            "{dev} offline for everyone", "nobody can print at {site}", "{dev} not showing up",
            "printer down at station",
        ],
        "details": [
            "Nobody at {site} can print to the {dev} since the power went out last night.",
            "The {dev} shows offline on every computer at {site}.",
        ],
        "resolutions": [
            "Copier picked up a new IP after the power outage. Set a DHCP reservation and updated the port on the print server.",
            "Copier network cable was unplugged during cleaning. Reconnected it, printer back online for everyone.",
            "Switch port the copier was on had failed. Moved it to a working port, online.",
        ],
    },
    {
        "key": "printer_hw", "count": 14, "type": "Hardware", "subtype": "Printer",
        "assets": ["Ricoh IM C3000", "Brother MFC-L8900"], "device": PRINTER, "impact": 2, "urgency": 3,
        "summaries": [
            "{dev} jammed again??", "paper jam", "{dev} making grinding noise", "prints have streaks",
            "{dev} error SC542",
        ],
        "details": [
            "{dev} keeps jamming in tray 2. Cleared it 3 times today.",
            "Prints coming out with black streaks down the page.",
            "copier showing a service code and wont print anything",
        ],
        "resolutions": [
            "Replaced fuser unit; opened vendor ticket with Ricoh for the follow-up PM.",
            "Pickup rollers in tray 2 worn. Cleaned the rollers and ordered a replacement kit, jams stopped.",
            "Drum unit at end of life causing streaks. Replaced drum, print quality good.",
            "Service code SC542 (fuser). Ricoh tech dispatched under the service contract, fuser replaced.",
        ],
    },
    {
        "key": "scan_email", "count": 8, "type": "Hardware", "subtype": "Scanners",
        "assets": ["Ricoh IM C3000"], "device": PRINTER, "impact": 2, "urgency": 2,
        "summaries": ["scan to email not working", "copier scans not coming thru", "cant scan to my email"],
        "details": [
            "Scanning to email from the {dev} says 'transmission failed'.",
            "We scan our run sheets to email and nothing has arrived since Monday.",
        ],
        "resolutions": [
            "Scanner service account password expired. Updated the SMTP credentials in the copier settings, test scan delivered.",
            "M365 disabled basic SMTP auth for the scanner account. Switched the copier to the SMTP relay connector, scans delivering.",
        ],
    },
    {
        "key": "password_reset", "count": 20, "type": "Account Administration", "subtype": "Password Reset",
        "impact": 3, "urgency": 2,
        "summaries": [
            "locked out", "forgot my password", "cant log in to computer", "password expired",
            "Account locked", "cant login",
        ],
        "details": [
            "I'm locked out of my account, tried my password a few times.",
            "Password expired over the weekend and now it won't let me log in at {site}.",
            "Can't log in, says the referenced account is currently locked out.",
        ],
        "resolutions": [
            "Verified identity via callback, unlocked the AD account and reset the password. User changed it at next logon.",
            "Account kept locking from an old password cached on the user's phone. Updated the password in mobile Outlook and unlocked.",
            "Reset password in Entra, synced to AD, user signed in successfully.",
        ],
    },
    {
        "key": "mfa_phone", "count": 10, "type": "Account Administration", "subtype": "Account Information Change",
        "impact": 3, "urgency": 2,
        "summaries": [
            "new phone need authenticator", "mfa not working new phone", "authenticator app codes",
            "cant approve sign in",
        ],
        "details": [
            "Got a new phone and now I can't approve the Microsoft sign-in.",
            "Authenticator app isn't getting the prompts anymore.",
        ],
        "resolutions": [
            "Cleared MFA methods in Entra, user re-registered Microsoft Authenticator on the new phone.",
            "Required MFA re-registration and walked the user through Authenticator setup. Sign-in approved.",
        ],
    },
    {
        "key": "alerting_tones", "count": 14, "type": "Hardware", "subtype": "Speakers",
        "impact": 1, "urgency": 1,
        "summaries": [
            "tones didnt drop at {site}", "station alerting not working", "no tones last call",
            "alerting system no audio in bay", "bay speakers silent",
        ],
        "details": [
            "Station alerting didn't go off for the last call at {site}. Crew heard it on the radio only.",
            "No audio from the bay speakers when tones drop. Lights come on though.",
            "Alerting isn't announcing in the dorms at {site}.",
        ],
        "resolutions": [
            "Alerting amp in the bay had lost power. Reset the breaker, ran a test tone from dispatch, all zones good.",
            "Station alerting controller lost its connection to the CAD interface. Restarted the alerting service on the station controller, test alert confirmed.",
            "Dorm zone amplifier failed. Swapped the amp with a spare, test alert played in all zones.",
        ],
    },
    {
        "key": "g2_config", "count": 8, "type": "Account Administration", "subtype": "G2 Alerting Configuration",
        "impact": 3, "urgency": 3,
        "summaries": [
            "add member to alerting", "need new guy added to G2 alerts", "remove old member from alerting group",
            "alert texts not coming",
        ],
        "details": [
            "Please add our new member to the station alerting text group for {site}.",
            "Not getting the alert texts on my phone anymore.",
        ],
        "resolutions": [
            "Added the user to the {site} alert group in G2 config and sent a test page.",
            "User's cell number had a typo in G2. Corrected the number, test alert received.",
        ],
    },
    {
        "key": "truck_modem", "count": 10, "type": "Hardware", "subtype": "Gateway/Router",
        "assets": ["Cradlepoint IBR900", "Sierra Wireless MG90"], "impact": 3, "urgency": 1,
        "summaries": [
            "hotspot in {unit} not working", "no internet in {unit}", "modem lights blinking",
            "truck wifi down",
        ],
        "details": [
            "The truck wifi in {unit} isn't working, tablets can't get online.",
            "Modem in {unit} has a red light and nothing connects.",
        ],
        "resolutions": [
            "Carrier deactivated the SIM. Swapped the SIM, confirmed LTE and truck Wi-Fi working.",
            "Modem firmware hung. Rebooted from NetCloud and scheduled the firmware update, connectivity restored.",
            "Modem power lead loose behind the console. Reseated it, modem online.",
        ],
    },
    {
        "key": "station_wifi", "count": 14, "type": "Network", "subtype": "WiFi Outage",
        "assets": ["UniFi U6-Lite", "UniFi U6-Pro"], "impact": 2, "urgency": 2,
        "summaries": [
            "wifi down at {site}", "internet slow in the day room", "wireless keeps dropping", "no wifi in bay",
            "wifi not working",
        ],
        "details": [
            "Wi-Fi at {site} keeps dropping, especially in the day room.",
            "No wifi in the apparatus bay so the trucks can't sync.",
            "internet super slow at {site} on the wireless",
        ],
        "resolutions": [
            "UniFi AP in the day room was offline from a flapping PoE port. Moved the AP to a new switch port and re-adopted it in the controller.",
            "DHCP scope was exhausted. Shortened the lease time and expanded the scope, clients connecting.",
            "Failed UniFi AP in the apparatus bay. Replaced it with a spare U6-Lite and adopted.",
        ],
    },
    {
        "key": "outlook_password", "count": 10, "type": "Standard Applications", "subtype": "Outlook",
        "impact": 3, "urgency": 2,
        "summaries": [
            "outlook keeps asking for password", "outlook password prompt", "email keeps asking me to sign in",
        ],
        "details": [
            "Outlook pops up asking for my password every few minutes.",
            "Keep getting the sign in window in Outlook even after I put my password in.",
        ],
        "resolutions": [
            "Cleared cached credentials in Credential Manager and rebuilt the Outlook profile.",
            "Removed a stale work account from Windows 'Access work or school' and signed back in. Prompts stopped.",
        ],
    },
    {
        "key": "mailbox_full", "count": 8, "type": "Standard Applications", "subtype": "Email",
        "impact": 3, "urgency": 2,
        "summaries": ["mailbox full", "cant send email", "email bouncing back", "outlook says mailbox almost full"],
        "details": [
            "Outlook says my mailbox is full and I can't send anything.",
            "Emails I send are bouncing back saying the mailbox is over quota.",
        ],
        "resolutions": [
            "Mailbox at quota. Enabled the online archive and applied the archive retention policy.",
            "Cleared deleted items and large attachments with the user and enabled the online archive.",
        ],
    },
    {
        "key": "shared_mailbox", "count": 8, "type": "Account Administration", "subtype": "Mail Access",
        "impact": 3, "urgency": 3,
        "summaries": ["need access to {site} shared inbox", "add me to the station email", "shared mailbox not showing"],
        "details": [
            "Can I get access to the {site} shared mailbox? Captain approved.",
            "I was given access to the station inbox but it doesn't show up in Outlook.",
        ],
        "resolutions": [
            "Granted Full Access and Send As on the shared mailbox; it showed up in Outlook after a restart.",
            "Permissions were in place but automapping failed. Added the mailbox manually in Outlook.",
        ],
    },
    {
        "key": "dock_monitors", "count": 10, "type": "Hardware", "subtype": "Docking Station",
        "assets": ["Dell WD19", "Dell WD22TB4"], "impact": 3, "urgency": 2,
        "summaries": [
            "monitors not working when docked", "second screen black", "dock not detecting monitors",
            "docking station issue",
        ],
        "details": [
            "When I plug my laptop into the dock at {site} the monitors stay black.",
            "Only one of my two monitors works with the dock.",
        ],
        "resolutions": [
            "Updated the Dell dock firmware and DisplayLink driver; both monitors detected.",
            "Dock was on the wrong power brick. Replaced with the 180W supply, monitors working.",
        ],
    },
    {
        "key": "monitor_hw", "count": 6, "type": "Hardware", "subtype": "Monitor",
        "impact": 3, "urgency": 3,
        "summaries": ["monitor flickering", "screen flickers", "monitor wont turn on", "lines on monitor"],
        "details": ["My monitor keeps flickering on and off.", "Monitor has lines across it and goes black."],
        "resolutions": [
            "Replaced the DisplayPort cable, flicker gone.",
            "Monitor backlight failed. Replaced the monitor from stock.",
        ],
    },
    {
        "key": "phishing", "count": 12, "type": "IT Security Threats", "subtype": "Phishing Email",
        "impact": 3, "urgency": 1,
        "summaries": [
            "is this email legit?", "weird email asking me to sign in", "suspicious email",
            "got phishing email", "fake invoice email",
        ],
        "details": [
            "Got an email saying my password expires today with a link. Doesn't look right.",
            "Email from 'the chief' asking me to buy gift cards??",
            "Got an invoice from a vendor we don't use with an attachment.",
        ],
        "resolutions": [
            "Confirmed phishing. Purged the message from all mailboxes and blocked the sender domain. User did not click the link.",
            "Reported phish. Removed from the tenant via Threat Explorer; user confirmed no credentials were entered.",
        ],
    },
    {
        "key": "desk_phone", "count": 8, "type": "Telephony", "subtype": "Yealink RPS",
        "assets": ["Yealink T54W", "Yealink T46U"], "impact": 3, "urgency": 2,
        "summaries": ["phone not working", "desk phone says no service", "phone at {site} no dial tone", "phone shows network unavailable"],
        "details": [
            "Desk phone at {site} has no dial tone and says network unavailable.",
            "The phone in the watch office isn't working since this morning.",
        ],
        "resolutions": [
            "Yealink lost provisioning after the PoE switch reboot. Re-provisioned via RPS, phone registered.",
            "Phone cable was unplugged from the wall jack. Reconnected, phone registered.",
        ],
    },
    {
        "key": "new_hire", "count": 6, "type": "Account Administration", "subtype": "New Account",
        "impact": 3, "urgency": 3,
        "summaries": ["new hire starting monday", "new member account", "probie needs accounts"],
        "details": [
            "We have a new firefighter starting Monday at {site}, needs email and computer login.",
            "New member starting next week, please set up accounts.",
        ],
        "resolutions": [
            "Created AD/M365 account, added to station security and distribution groups, requested CAD and ePCR accounts from the vendors.",
            "Account created and licensed, credentials sent to the captain, added to the {site} alert group.",
        ],
    },
    {
        "key": "training_tv", "count": 6, "type": "Hardware", "subtype": "Airtame",
        "impact": 2, "urgency": 3,
        "summaries": ["training room tv not working", "cant cast to tv", "airtame not showing up"],
        "details": [
            "Trying to put a presentation on the training room TV and the Airtame doesn't show up.",
            "TV in the training room just says no signal.",
        ],
        "resolutions": [
            "Airtame needed a firmware update; updated and rejoined Wi-Fi, casting works.",
            "TV was on the wrong HDMI input. Set to HDMI 2 and labeled the remote.",
        ],
    },
]

# Back-and-forth for each scenario: technician private notes, questions emailed to the user, and
# the user's replies. Anything missing falls back to the GENERIC_* pools below.
THREADS: dict[str, dict[str, list[str]]] = {
    "cad_modem": {
        "notes": [
            "NetCloud shows the {unit} modem offline since early this morning. Last check-in had weak LTE signal.",
            "Checked the CAD server, other units are connected fine. Issue isolated to {unit}.",
            "Remoted into the {dev} while the rig was on station Wi-Fi. CAD client config looks fine, pointing at the modem.",
        ],
        "asks": [
            "Can you check the Cradlepoint under the passenger seat in {unit}? What color are the power and signal lights?",
            "Is {unit} in quarters right now? I'd like to remote in while it's on the station Wi-Fi.",
            "Does the {dev} show any network in the bottom right, or the globe icon with no connection?",
        ],
        "answers": [
            "power is green, the signal light is off",
            "in quarters now, go ahead",
            "globe icon no internet. wifi works in the bay tho",
            "rig is out on a call, back around 1500. will let you know",
        ],
    },
    "cad_vpn": {
        "notes": [
            "VPN server logs show repeated failed tunnel attempts from this device.",
            "Intune shows the device certificate expired.",
            "Other units are connecting to the VPN fine, so it's this device.",
        ],
        "asks": [
            "Can you send me a picture of the error on the VPN client?",
            "Can the {dev} get on the internet otherwise? Try opening any website.",
        ],
        "answers": [
            "it says the certificate is not valid or something",
            "internet works, just vpn and cad dont",
            "pic attached",
        ],
    },
    "cad_crash": {
        "notes": [
            "Windows Update history shows the latest cumulative update installed overnight.",
            "Event Viewer shows a .NET runtime error from the CAD client at launch.",
            "Checked two other units on the same update, CAD launches fine there.",
        ],
        "asks": [
            "Does the error come up right when you open CAD, or after you log in?",
            "Can you leave the {dev} powered on and docked so I can remote in?",
        ],
        "answers": [
            "right when we open it, doesnt even get to the login",
            "its docked and on, go ahead",
            "after login it just closes",
        ],
    },
    "cad_unit_id": {
        "notes": [
            "Confirmed with dispatch that {unit} is showing up as {unit2} in CAD.",
            "Asset records show this {dev} was assigned to {unit2} until last week.",
        ],
        "asks": [
            "Which rig is the {dev} physically in right now, and can you read me the asset tag on the bottom?",
            "Did the {dev} get swapped between trucks recently?",
        ],
        "answers": [
            "its in {unit}. tag is on the bottom, will check when we get back",
            "yeah we moved it from {unit2} last shift because the other one died",
        ],
    },
    "vehicle_dock": {
        "notes": [
            "Dispatched a field tech to {site} for the vehicle dock.",
            "Checked stock, we have spare dock power cables and inline fuses.",
        ],
        "asks": [
            "Are there any lights on the dock when the rig is running?",
            "When can we get hands on {unit}? It needs to be in quarters for about 30 minutes.",
        ],
        "answers": [
            "no lights at all",
            "light flickers when you push on the {dev}",
            "should be in quarters after 1300",
        ],
    },
    "toughbook_touch": {
        "notes": [
            "Touch driver is behind the current Panasonic release.",
            "Remote session: touch input is registering about 2cm off from where you tap.",
        ],
        "asks": [
            "Does touch work in some spots and not others, or not at all?",
            "Is there a screen protector on the {dev}?",
        ],
        "answers": [
            "works on the left side but not the right",
            "not at all",
            "yes theres a protector, its kind of bubbled up",
        ],
    },
    "toughbook_power": {
        "notes": [
            "Battery report shows full charge capacity at 41% of design capacity.",
            "Checked warranty in the Panasonic portal, battery is covered.",
        ],
        "asks": [
            "Does the power light come on at all when you press the button?",
            "Roughly how long does the battery last now on a full charge?",
        ],
        "answers": ["no light nothing", "maybe an hour", "orange light blinks then nothing"],
    },
    "epcr_sync": {
        "notes": [
            "ePCR admin portal shows this device last synced yesterday afternoon.",
            "Vendor status page shows no outage.",
            "Confirmed {k} reports sitting in the local queue on the device.",
        ],
        "asks": [
            "How many reports are showing as pending, and what does the error say when it tries to sync?",
            "Is the {dev} on the station Wi-Fi or the truck LTE when it tries to sync?",
        ],
        "answers": [
            "{k} pending, says sync failed try again later",
            "on truck lte, we tried at the station too",
            "error says unauthorized",
        ],
    },
    "epcr_print": {
        "notes": [
            "Default printer on the device is set to the admin office copier.",
            "Print server shows no jobs received from this device.",
        ],
        "asks": ["Which printer are you trying to print to?", "Does printing work from other programs on that computer?"],
        "answers": ["the one in the station office", "other stuff prints fine, just not epcr"],
    },
    "printer_driver": {
        "notes": [
            "Print queue on the PC shows {k} jobs stuck in error.",
            "Driver on the PC is the generic Microsoft class driver, not the Ricoh one.",
        ],
        "asks": [
            "Can other people at {site} print to the {dev}?",
            "Can you send me the computer name? It's on the sticker on the front of the PC.",
        ],
        "answers": ["yes everyone else is fine", "sticker is gone, its the one by the window", "not sure, i think so"],
    },
    "printer_offline": {
        "notes": [
            "Can't ping the copier's IP from the station switch.",
            "DHCP leases show the copier picked up a new address.",
        ],
        "asks": [
            "Is the copier's screen on, and does it show any network error?",
            "Could you power cycle the copier and let me know if it shows up?",
        ],
        "answers": ["screen is on no errors", "power cycled it, still offline", "theres a little icon with an x on it"],
    },
    "printer_hw": {
        "notes": ["Copier meter read shows it's past the PM interval.", "Logged a service call with Ricoh."],
        "asks": [
            "Is it jamming in the same spot every time? A photo of the error screen would help.",
            "Is there a service code showing on the screen?",
        ],
        "answers": ["tray 2 every time", "SC542 on the screen", "photo attached"],
    },
    "scan_email": {
        "notes": ["SMTP logs show auth failures from the scanner account.", "Scanner account password was last set 90+ days ago."],
        "asks": [
            "What happens when you scan? Any error on the copier screen?",
            "Who are you scanning to, your own email or a group?",
        ],
        "answers": ["says transmission failed", "to my email and the captains"],
    },
    "password_reset": {
        "notes": [
            "Sign-in logs show repeated failed attempts from a mobile device.",
            "Verified identity via callback to the number on file.",
        ],
        "asks": [
            "I need to verify your identity before resetting. What's the best number to call you at?",
            "Do you have work email on your phone? It may still have your old password saved.",
        ],
        "answers": ["call me at the station", "yes on my phone", "i changed it last week i think"],
    },
    "mfa_phone": {
        "notes": ["Entra shows MFA registered to the old device only.", "User confirmed the old phone was traded in."],
        "asks": ["Do you still have your old phone?", "Are you near a computer? I can walk you through re-registering."],
        "answers": ["no traded it in", "yes at the station computer now"],
    },
    "alerting_tones": {
        "notes": [
            "Called dispatch, they confirmed tones were sent for the last call.",
            "Alerting controller at {site} isn't responding on its management IP.",
            "Alerting logs show the bay zone failed to acknowledge.",
        ],
        "asks": [
            "Did the lights come on in the bay, or nothing at all?",
            "Can you check whether the amp rack in the watch office has power lights?",
        ],
        "answers": ["lights came on no audio", "amp has no lights", "nothing at all, we got it on the radio"],
    },
    "g2_config": {
        "notes": ["Verified the member is active on the roster."],
        "asks": ["Can you send the member's cell number and carrier?", "Which station groups should they be in?"],
        "answers": ["will send it over, its verizon", "just {site} for now"],
    },
    "truck_modem": {
        "notes": ["NetCloud shows the {unit} modem offline.", "Carrier portal shows the SIM status as deactivated."],
        "asks": ["Is the modem showing any lights?", "Is the rig in quarters so I can check it remotely?"],
        "answers": ["red light on it", "in quarters now"],
    },
    "station_wifi": {
        "notes": [
            "UniFi controller shows the bay AP disconnecting every few minutes.",
            "Switch port for the AP is logging PoE errors.",
        ],
        "asks": [
            "Is it the whole station or just certain rooms?",
            "Did anything change recently, like a power outage or work in the building?",
        ],
        "answers": ["mostly the day room and the bay", "power blipped thursday during the storm"],
    },
    "outlook_password": {
        "notes": ["Sign-in logs show successful auth but the token refresh failing."],
        "asks": ["Is this on the station PC or your own laptop?", "Does it happen in Outlook on the web too?"],
        "answers": ["station pc", "web works fine"],
    },
    "mailbox_full": {
        "notes": ["Mailbox is at 49.8 GB of 50 GB."],
        "asks": ["OK to turn on archiving? Older mail moves to an Archive folder, nothing gets deleted."],
        "answers": ["yes thats fine", "sure go ahead"],
    },
    "shared_mailbox": {
        "notes": ["Captain approved the access by email."],
        "asks": ["Which shared mailbox, and do you need to send as it or just read it?"],
        "answers": ["station inbox, yes need to send from it", "just read"],
    },
    "dock_monitors": {
        "notes": ["DisplayLink driver on the laptop is out of date."],
        "asks": [
            "Which dock are you using? The model is on the bottom.",
            "Do the monitors work if you plug them straight into the laptop?",
        ],
        "answers": ["WD19 i think", "yes they work direct"],
    },
    "monitor_hw": {
        "asks": ["Does it flicker all the time or only sometimes?"],
        "answers": ["all the time", "only when i move the cable"],
    },
    "phishing": {
        "notes": [
            "Message trace shows the email went to 14 users across the tenant.",
            "Sender domain was registered 3 days ago.",
        ],
        "asks": ["Did you click the link or enter your password anywhere?", "Can you forward the email to us as an attachment?"],
        "answers": ["no i didnt click anything", "forwarded", "i clicked it but didnt type anything"],
    },
    "desk_phone": {
        "notes": ["RPS shows the phone hasn't checked in since the switch reboot."],
        "asks": ["Is the phone's screen lit up?", "Can you check that the cable on the back is clicked in?"],
        "answers": ["screen says network unavailable", "cable was loose, still not working"],
    },
    "new_hire": {
        "notes": ["Waiting on HR to confirm the start date."],
        "asks": ["Can you send the new member's full name, start date and station?"],
        "answers": ["sent it over, starting at {site}"],
    },
    "training_tv": {
        "asks": ["Is the Airtame plugged into the TV and showing its screen?"],
        "answers": ["tv says no signal", "the airtame screen shows but my laptop cant find it"],
    },
}
GENERIC_NOTES = [
    "Reviewed previous tickets for this site, nothing similar recently.",
    "Remote session scheduled with the user.",
    "Escalated to Field Services for an onsite visit.",
]
GENERIC_ASKS = [
    "When did this start, and is anyone else at {site} seeing it?",
    "Can you send a screenshot of the error?",
    "Are you free for a quick remote session this afternoon?",
]
GENERIC_ANSWERS = ["started this morning, just me i think", "screenshot attached", "yes im here until 1700"]
PHONE_NOTES = [
    "Called {first} at {site} and went over the issue. Following up by email.",
    "Left a voicemail for {first}, sent an email as well.",
    "Spoke with {first}, they're on shift until 0700 so following up by email.",
]
NUDGES = [
    "Just checking in on this. Are you still seeing the issue?",
    "Following up, let me know when you have a minute to look at this.",
]
LATE_PREFIXES = ["sorry was on shift. ", "sorry for the delay, ", "just saw this. ", ""]
CONFIRM_ASKS = [
    "I've made a fix on our end. Can you try again and let me know if it's working?",
    "This should be sorted now. Please give it a test when you get a chance.",
    "We've made a change. Can you confirm it's working before we close this out?",
]
CONFIRM_REPLIES = [
    "working now thanks!!", "yep all good", "That fixed it, thank you", "looks good. thanks for the quick help",
    "seems ok now, will let you know if it comes back",
]

VAGUE_SUMMARIES = [
    "its broken again", "not working", "help!!", "issue at {site}", "computer problem", "URGENT",
    "same problem as last week", "please call me", "IT issue", "having issues",
]
NON_EMAIL_CHANNELS = ["Manual - Phone", "Manual - Phone", "Portal", "Manual"]
SHORT_RESOLUTIONS = ["fixed", "done", "resolved", "working now", "user fixed it", "see notes", "rebooted"]

FIRST_NAMES = [
    "Dana", "Marcus", "Kelly", "Ruben", "Tasha", "Owen", "Priya", "Hank", "Lena", "Derek", "Carla",
    "Mitch", "Jenna", "Victor", "Shawna", "Eli", "Rosa", "Grant", "Nadia", "Cody",
]
LAST_NAMES = [
    "Halvorsen", "Okafor", "Brennan", "Villarreal", "Pruitt", "Castellano", "Moody", "Tran", "Fairbanks",
    "Kowalski", "Ruiz", "Dempsey", "Whitaker", "Sandoval", "Lindqvist", "Abernathy",
]
TITLES = [
    "Firefighter/EMT", "Captain", "Lieutenant", "Paramedic", "Battalion Chief", "Admin Assistant",
    "EMS Coordinator", "Fire Marshal",
]
GREETINGS = ["Hi team,", "Hello,", "Good morning,", "Hey IT,", "Hi,"]
SIGN_OFFS = ["Thanks,", "Thank you,", "Regards,", "Respectfully,", "V/r,"]
CAUTION = (
    "CAUTION: This email originated from outside of the organization. Do not click links or open "
    "attachments unless you recognize the sender and know the content is safe."
)
CONFIDENTIALITY = (
    "CONFIDENTIALITY NOTICE: This e-mail and any attachments are intended only for the named "
    "recipient and may contain protected health information."
)

# Open tickets for the demo (seeded directly, so no note; open their Similar Tickets tab).
# "thread" entries are (hours after reported, outcome, "agent" | "user", note, hidden from user).
OPEN_TICKETS = [
    dict(summary="printer at station 6 jammed again??", client="Cedar County EMS", site="Station 6",
         user="Marcus Okafor", type="Hardware", subtype="Printer", asset="Ricoh IM C3000",
         impact=2, urgency=3, age_hours=20, status="In Progress", channel="Email",
         details="Copier in the office keeps jamming, cleared it twice already.\n\nSent from my iPhone",
         thread=[
             (1.5, "Email User", "agent", "Hi Marcus,\n\nThanks for letting us know. Which tray is it jamming from, and is there an error code on the screen?\n\nThanks,\nService Desk", False),
             (3.0, "Customer Reply", "user", "tray 2 every time. no code just says paper jam\n\nSent from my iPhone", False),
         ]),
    dict(summary="epcr not uploading reports", client="Lakeview Fire & Rescue", site="Station 9",
         user="Rosa Ruiz", type="Standard Applications", subtype="Web App", asset=None,
         impact=3, urgency=1, age_hours=5, status="In Progress", channel="Email",
         details="Hi team,\n\nMedic 9 has 3 reports that won't send to the hospital, keeps saying pending.\n\nThanks,\nLt. Rosa Ruiz\nLakeview Fire & Rescue\n(555) 410-2231",
         thread=[
             (0.5, "Private Note", "agent", "Called station, no answer. Will try the Medic 9 crew cell after shift change.", True),
         ]),
    dict(summary="cant get into email on new phone", client="Riverside Fire Dept", site="Admin Office",
         user="Kelly Brennan", type="Account Administration", subtype="Account Information Change", asset=None,
         impact=3, urgency=3, age_hours=30, status="Waiting on User", channel="Portal",
         details="got a new phone and the microsoft app wont let me approve anything",
         thread=[
             (2.0, "Email User", "agent", "Hi Kelly,\n\nDo you still have your old phone? If so we can move the Authenticator over without a reset.\n\nThanks,\nService Desk", False),
         ]),
    dict(summary="tones didnt go off at stn 11 last night", client="Pine Ridge Fire District", site="Station 11",
         user="Hank Dempsey", type="Hardware", subtype="Speakers", asset=None,
         impact=1, urgency=1, age_hours=2.5, status="New", channel="Manual - Phone",
         details="Bay speakers were silent for the 0200 call, lights came on. Crew caught it on the radio.",
         thread=[
             (0.3, "Phone Call", "agent", "Called Hank at Station 11. Lights came on in the bay, no audio. Dorms were fine. Asked him to check the amp rack.", True),
             (0.5, "Private Note", "agent", "Called dispatch, they confirmed tones went out for the 0200 call. Alerting logs show the bay zone failed to acknowledge.", True),
             (1.6, "Customer Reply", "user", "amp in the watch office has no lights on it. breaker looks ok\n\nSent from my iPhone", False),
         ]),
    dict(summary="wifi in the bay keeps dropping", client="Riverside Fire Dept", site="Station 2",
         user="Derek Pruitt", type="Network", subtype="WiFi Outage", asset="UniFi U6-Lite",
         impact=2, urgency=2, age_hours=3, status="New", channel="Portal",
         details="trucks wont sync in the bay, wifi drops every few min",
         thread=[
             (0.4, "Private Note", "agent", "UniFi controller shows the bay AP (U6-Lite) disconnecting every 3-5 minutes since yesterday afternoon.", True),
             (0.6, "Email User", "agent", "Hi Derek,\n\nThanks, we can see the access point in the bay dropping off. Did anything change at the station recently, like a power outage or work in the bay?\n\nThanks,\nService Desk", False),
         ]),
]


class Generator:
    def __init__(self, seed: int = RNG_SEED):
        self.rng = random.Random(seed)
        # Threads draw from their own stream so adding them doesn't change the tickets themselves.
        self.trng = random.Random(seed + 1)

    def pick(self, items):
        return self.rng.choice(items)

    def person(self) -> tuple[str, str]:
        return self.pick(FIRST_NAMES), self.pick(LAST_NAMES)

    def typo(self, word: str, rng: random.Random | None = None) -> str:
        rng = rng or self.rng
        i = rng.randrange(1, len(word) - 1)
        op = rng.choice(("drop", "swap", "double"))
        if op == "drop":
            return word[:i] + word[i + 1:]
        if op == "swap":
            return word[:i] + word[i + 1] + word[i] + word[i + 2:]
        return word[:i] + word[i] + word[i:]

    def add_typos(self, text: str, rate: float, rng: random.Random | None = None) -> str:
        rng = rng or self.rng
        return re.sub(r"[A-Za-z]{5,}", lambda m: self.typo(m.group(), rng) if rng.random() < rate else m.group(), text)

    # --- threads ---------------------------------------------------------------------------

    def agent_email(self, first: str, body: str, agent: str) -> str:
        return f"Hi {first},\n\n{body}\n\nThanks,\n{agent.split()[0]}\nService Desk"

    def user_reply(self, text: str) -> str:
        r = self.trng
        text = self.add_typos(text, 0.04, r)
        if r.random() < 0.15:
            text = text[0].upper() + text[1:]
        if r.random() < 0.3:
            text += "\n\nSent from my iPhone"
        return text

    def build_thread(
        self, scenario: dict, ctx: dict, user: tuple[str, str], agent: str, helper: str | None,
        channel: str, reported: datetime,
    ) -> list[tuple[datetime, str, str, str, bool]]:
        """A realistic back-and-forth: (when, outcome, who, note, hidden from user)."""
        r = self.trng
        content = THREADS.get(scenario["key"], {})
        notes = r.sample(content.get("notes") or GENERIC_NOTES, k=len(content.get("notes") or GENERIC_NOTES))
        ask = r.choice(content.get("asks") or GENERIC_ASKS)
        answer = r.choice(content.get("answers") or GENERIC_ANSWERS)
        first = user[0]
        ctx = {**ctx, "first": first}
        events: list[tuple[float, str, str, str, bool]] = []  # (hours gap, outcome, who, note, hidden)

        def agent_gap() -> float:
            return r.uniform(0.1, 1.5)

        if channel == "Manual - Phone" or r.random() < 0.15:
            events.append((agent_gap(), "Phone Call", agent, self.fill(r.choice(PHONE_NOTES), ctx), True))
        if r.random() < 0.65:
            events.append((agent_gap(), "Private Note", agent, self.fill(notes.pop(0), ctx), True))
        if r.random() < 0.8:
            events.append((agent_gap(), "Email User", agent, self.agent_email(first, self.fill(ask, ctx), agent), False))
            late = r.random() < 0.2
            if late:  # user went quiet; nudge them
                events.append((r.uniform(20, 28), "Email User", agent, self.agent_email(first, r.choice(NUDGES), agent), False))
            reply = (r.choice(LATE_PREFIXES[:-1]) if late else "") + self.fill(answer, ctx)
            events.append((r.uniform(0.3, 6), "Customer Reply", " ".join(user), self.user_reply(reply), False))
            if notes and r.random() < 0.45:
                who = helper if helper and r.random() < 0.5 else agent
                events.append((agent_gap(), "Private Note", who, self.fill(notes.pop(0), ctx), True))
        if r.random() < 0.6:
            events.append((agent_gap(), "Email User", agent, self.agent_email(first, r.choice(CONFIRM_ASKS), agent), False))
            if r.random() < 0.85:
                events.append((r.uniform(0.2, 5), "Customer Reply", " ".join(user), self.user_reply(r.choice(CONFIRM_REPLIES)), False))

        thread, when = [], reported
        for gap, outcome, who, note, hidden in events:
            when += timedelta(hours=gap)
            thread.append((when, outcome, who, note, hidden))
        return thread

    def fill(self, template: str, ctx: dict) -> str:
        return template.format(**ctx)

    def messy_summary(self, scenario: dict, ctx: dict) -> str:
        if self.rng.random() < 0.08:
            summary = self.fill(self.pick(VAGUE_SUMMARIES), ctx)
        else:
            summary = self.add_typos(self.fill(self.pick(scenario["summaries"]), ctx), 0.06)
        roll = self.rng.random()
        if roll < 0.25:
            summary = summary.lower()
        elif roll < 0.29:
            summary = summary.upper()
        elif roll < 0.4:
            summary = "RE: " + summary
        return summary

    def messy_details(self, scenario: dict, ctx: dict, user: tuple[str, str], client: str) -> tuple[str, str]:
        """Returns (details, channel)."""
        body = self.add_typos(self.fill(self.pick(scenario["details"]), ctx), 0.03)
        if self.rng.random() < 0.3:
            body = body.lower()
        if self.rng.random() > 0.45:  # not every ticket comes in by email
            return body, self.pick(NON_EMAIL_CHANNELS)
        first, last = user
        domain = CLIENTS[client]["domain"]
        parts = []
        if self.rng.random() < 0.15:
            parts.append(CAUTION)
        if self.rng.random() < 0.6:
            parts.append(self.pick(GREETINGS))
        parts.append(body)
        if self.rng.random() < 0.7:
            parts.append(
                f"{self.pick(SIGN_OFFS)}\n{first} {last}\n{self.pick(TITLES)} | {client}\n"
                f"(555) {self.rng.randint(200, 999)}-{self.rng.randint(1000, 9999)}"
            )
        if self.rng.random() < 0.25:
            parts.append("Sent from my iPhone")
        if self.rng.random() < 0.05:
            parts.append(CONFIDENTIALITY)
        text = "\n\n".join(parts)
        if self.rng.random() < 0.12:  # forwarded on behalf of a crew member
            fwd_first, fwd_last = self.person()
            text = (
                f"FYI see below, can someone look at this\n\n"
                f"From: {first} {last} <{first.lower()}.{last.lower()}@{domain}>\n"
                f"Sent: {ctx['sent']}\nTo: {fwd_first} {fwd_last} <{fwd_first.lower()}.{fwd_last.lower()}@{domain}>\n"
                f"Subject: {ctx['summary']}\n\n{text}"
            )
        return text, "Email"

    def resolution(self, scenario: dict, ctx: dict) -> str:
        roll = self.rng.random()
        if roll < 0.05:
            return ""
        if roll < 0.11:
            return self.pick(SHORT_RESOLUTIONS)
        return self.fill(self.pick(scenario["resolutions"]), ctx)

    def team_for(self, ticket_type: str) -> str:
        return {
            "Hardware": self.pick(["Field Services", "Service Desk"]),
            "Network": "Network",
            "IT Security Threats": "Security",
        }.get(ticket_type, "Service Desk")

    def closed_ticket(self, scenario: dict, now: datetime) -> dict:
        client = self.pick(list(CLIENTS))
        c = CLIENTS[client]
        units = self.rng.sample(c["units"], 2)
        reported = now - timedelta(days=self.rng.uniform(2, 540), hours=self.rng.uniform(0, 12))
        ctx = {
            "site": self.pick(c["sites"]),
            "unit": units[0],
            "unit2": units[1],
            "dev": self.pick(scenario.get("device") or ["computer"]),
            "k": self.rng.randint(2, 6),
            "sent": reported.strftime("%A, %B %d, %Y %I:%M %p"),
        }
        ctx["summary"] = self.fill(self.pick(scenario["summaries"]), ctx)
        user = self.person()
        ticket_type, subtype = scenario["type"], scenario["subtype"]
        if self.rng.random() < 0.08:  # miscategorized at triage
            ticket_type = self.pick(list(TYPES))
            subtype = self.pick(TYPES[ticket_type])
        impact = scenario["impact"] if self.rng.random() > 0.2 else self.rng.randint(1, 3)
        urgency = scenario["urgency"] if self.rng.random() > 0.2 else self.rng.randint(1, 3)
        priority = db.priority_for(impact, urgency)
        resolution_target, sla_action = db.sla_dates(reported, priority)
        closed = reported + timedelta(hours=self.rng.uniform(0.3, 72))
        assets = scenario.get("assets")
        details, channel = self.messy_details(scenario, ctx, user, client)
        ticket = {
            "summary": self.messy_summary(scenario, ctx),
            "details": details,
            "channel": channel,
            "client_name": client,
            "site_name": ctx["site"],
            "user_name": f"{user[0]} {user[1]}",
            "type": ticket_type,
            "subtype": subtype,
            "impact": impact,
            "urgency": urgency,
            "priority": f"P{priority}",
            "status": db.CLOSED_STATUS,
            "team": self.team_for(ticket_type),
            "agent": self.pick(AGENTS),
            "additional_agent": self.pick(AGENTS) if self.rng.random() < 0.15 else None,
            "asset_model": self.pick(assets) if assets and self.rng.random() < 0.75 else None,
            "date_reported": reported.isoformat(timespec="seconds"),
            "last_action_date": closed.isoformat(timespec="seconds"),
            "resolution_target": resolution_target,
            "sla_action_date": sla_action,
            "time_taken": round(self.rng.uniform(0.25, 3.0), 2),
            "date_closed": closed.isoformat(timespec="seconds"),
            "_resolution": self.resolution(scenario, ctx),
            "_scenario": scenario["key"],
        }
        thread = self.build_thread(
            scenario, ctx, user, ticket["agent"], ticket["additional_agent"], channel, reported
        )
        if thread:
            # Close after the conversation ends, not in the middle of it.
            closed = max(closed, thread[-1][0] + timedelta(hours=self.trng.uniform(0.1, 1.0)))
            agent_actions = sum(1 for _, outcome, *_ in thread if outcome != "Customer Reply")
            ticket["time_taken"] = round(ticket["time_taken"] + 0.15 * agent_actions, 2)
        ticket["date_closed"] = ticket["last_action_date"] = closed.isoformat(timespec="seconds")
        ticket["_thread"] = thread
        return ticket

    def open_ticket(self, spec: dict, now: datetime) -> dict:
        reported = now - timedelta(hours=spec["age_hours"])
        priority = db.priority_for(spec["impact"], spec["urgency"])
        resolution_target, sla_action = db.sla_dates(reported, priority)
        agent = self.pick(AGENTS)
        thread = [
            (reported + timedelta(hours=h), outcome, agent if who == "agent" else spec["user"], note, hidden)
            for h, outcome, who, note, hidden in spec["thread"]
        ]
        last_action = thread[-1][0] if thread else reported
        return {
            "summary": spec["summary"], "details": spec["details"], "client_name": spec["client"],
            "site_name": spec["site"], "user_name": spec["user"], "type": spec["type"],
            "subtype": spec["subtype"], "impact": spec["impact"], "urgency": spec["urgency"],
            "priority": f"P{priority}", "status": spec["status"], "team": self.team_for(spec["type"]),
            "agent": agent, "additional_agent": None, "asset_model": spec["asset"],
            "date_reported": reported.isoformat(timespec="seconds"),
            "last_action_date": last_action.isoformat(timespec="seconds"),
            "resolution_target": resolution_target, "sla_action_date": sla_action,
            "time_taken": round(0.25 * len(thread), 2), "date_closed": None, "channel": spec["channel"],
            "_thread": thread,
        }


TICKET_COLUMNS = [
    "summary", "details", "client_name", "site_name", "user_name", "type", "subtype", "impact", "urgency",
    "priority", "status", "team", "agent", "additional_agent", "asset_model", "date_reported",
    "last_action_date", "resolution_target", "sla_action_date", "time_taken", "date_closed", "channel",
]
INSERT_ACTION = (
    "INSERT INTO actions (ticket_id, note, outcome, hiddenfromuser, who, datetime) VALUES (?, ?, ?, ?, ?, ?)"
)


def seed() -> dict[str, int]:
    gen = Generator()
    now = datetime.now()
    closed = [gen.closed_ticket(s, now) for s in SCENARIOS for _ in range(s["count"])]
    closed.sort(key=lambda t: t["date_reported"])
    open_ = [gen.open_ticket(spec, now) for spec in OPEN_TICKETS]

    path = db.db_path()
    if path.exists():
        path.unlink()
    db.init_db(path)
    labels: dict[int, str] = {}
    placeholders = ", ".join("?" for _ in range(len(TICKET_COLUMNS) + 1))
    insert = f"INSERT INTO tickets (id, {', '.join(TICKET_COLUMNS)}) VALUES ({placeholders})"
    with db.connect(path) as conn:
        for ticket_id, t in enumerate(closed + open_, start=FIRST_TICKET_ID):
            conn.execute(insert, [ticket_id] + [t[c] for c in TICKET_COLUMNS])
            if t["status"] == db.CLOSED_STATUS:
                labels[ticket_id] = t["_scenario"]
                conn.execute(INSERT_ACTION, (ticket_id, t["_resolution"], "Resolved", 0, t["agent"], t["date_closed"]))
            for when, outcome, who, note, hidden in t.get("_thread", []):
                conn.execute(
                    INSERT_ACTION,
                    (ticket_id, note, outcome, int(hidden), who, when.isoformat(timespec="seconds")),
                )
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LABELS_PATH.write_text(json.dumps(labels, indent=0), encoding="utf-8")
    return {"closed": len(closed), "open": len(open_)}


if __name__ == "__main__":
    counts = seed()
    print(f"Seeded mock Halo: {counts['closed']} closed + {counts['open']} open tickets -> {db.db_path()}")
